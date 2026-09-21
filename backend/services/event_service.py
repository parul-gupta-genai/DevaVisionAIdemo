from database.session import SessionLocal
from database.models.models import CameraEvent
from typing import Dict, Any, Tuple, Optional

# --- Dispatcher Handlers ---

def _handle_enterprise_safety(e_data: Dict, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    active_alerts = e_data.get("active_alerts", [])
    if "FIRE_DETECTED" in active_alerts:
        return "danger", "Fire Detected", None
    return None

def _snap(meta: dict) -> Optional[str]:
    """Normalises whichever snapshot key a plugin used into a served URL path."""
    for key in ("snapshot_file", "vehicle_snapshot", "plate_snapshot"):
        val = (meta or {}).get(key)
        if val:
            return val if str(val).startswith("/") else "/" + str(val)
    return None


# Zone severity (critical/warning/info) onto the feed's colour vocabulary.
_ZONE_SEVERITY = {"critical": "danger", "warning": "warning", "info": "info"}


def _zone_row(meta: dict, fallback: str) -> Tuple[str, str, Optional[str]]:
    """One feed row for a restricted-zone event, named after the zone."""
    # meta["zone"] is the polygon, not a name — reading it as a label printed
    # a list of coordinates into the description.
    zone = meta.get("zone_name") or "Restricted Zone"
    # An event with no severity predates per-zone rules, and used to be shown
    # red unconditionally. Default to that rather than quietly downgrading a
    # historical breach — the same choice the alert engine makes.
    colour = _ZONE_SEVERITY.get(str(meta.get("severity") or "").lower(), "danger")
    dwell = meta.get("dwell_seconds")
    detail = meta.get("description") or f"{zone} {fallback}"
    if fallback == "Loitering" and isinstance(dwell, (int, float)):
        detail = f"Loitering in {zone} ({int(dwell)}s)"
    return colour, detail, _snap(meta)


def _handle_restriction(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # Was absent from EVENT_DISPATCHER entirely, so every RESTRICTION_ALERT
    # fell through to the "Analytics Update" fallback and was dropped before
    # reaching the feed.
    for event in e_data:
        etype = event.get("event_type")
        if etype == "RESTRICTION_ALERT":
            return _zone_row(event.get("metadata") or {}, "Breach")
        if etype == "RESTRICTION_LOITERING":
            return _zone_row(event.get("metadata") or {}, "Loitering")
    return None


def _handle_carton(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    for event in e_data:
        if event.get("event_type") == "CARTON_COUNTED":
            meta = event.get("metadata") or {}
            return "info", f"Carton Counted (total {meta.get('total_cartons_counted', '?')})", _snap(meta)
    return None


def _handle_face(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Watchlist hits outrank routine recognitions in the feed."""
    hit = None
    seen = None
    for event in e_data:
        meta = event.get("metadata") or {}
        if event.get("event_type") == "WATCHLIST_HIT" and hit is None:
            severity = meta.get("severity") or "critical"
            hit = (severity if severity in ("critical", "warning", "info") else "danger",
                   f"Watchlist {meta.get('category', 'HIT')}: "
                   f"{meta.get('person_name', 'Unknown')}", _snap(meta))
        elif event.get("event_type") == "FACE_RECOGNISED" and seen is None:
            direction = meta.get("direction")
            action = ("Check-in" if direction == "IN"
                      else "Check-out" if direction == "OUT" else "Seen")
            seen = ("success", f"{action}: {meta.get('person_name', 'Unknown')}"
                    + (f" ({meta['person_code']})" if meta.get("person_code") else ""),
                    _snap(meta))
    # "danger" is the severity the UI colours red; WATCHLIST_HIT metadata
    # carries critical/warning/info, so map critical onto it.
    if hit is not None:
        return ("danger" if hit[0] == "critical" else hit[0], hit[1], hit[2])
    return seen


def _handle_visitor_events(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # A returning visitor, an expected arrival and a repeat unknown are the
    # three outcomes an operator acts on differently, so they get their own
    # rows rather than all reading "Visitor detected".
    for event in e_data if isinstance(e_data, list) else []:
        etype = event.get("event_type")
        meta = event.get("metadata") or {}
        name = meta.get("name") or "Visitor"
        visits = meta.get("visit_number") or meta.get("total_visits")
        if etype == "VISITOR_ARRIVED":
            host = meta.get("host_name")
            return ("success",
                    f"Expected visitor arrived: {name}"
                    + (f" (to see {host})" if host else ""), _snap(meta))
        if etype == "RETURNING_VISITOR":
            days = meta.get("days_since_previous")
            gap = f", last here {days:.0f} day{'s' if days and days >= 2 else ''} ago" \
                if isinstance(days, (int, float)) and days >= 1 else ""
            return ("info",
                    f"Returning visitor: {name}"
                    + (f" (visit {visits}{gap})" if visits else ""), _snap(meta))
        if etype == "REPEAT_UNKNOWN_PERSON":
            return ("warning",
                    f"Unregistered person seen again"
                    + (f" (appearance {visits})" if visits else ""), _snap(meta))
    return _handle_visitor(e_data, cam_name)


# SOW 2.8 vocabulary, most serious first. One stored row yields at most one
# feed entry per plugin, so the order here decides what an operator sees when
# a single pass confirms more than one thing: fire outranks smoke, and the
# all-clear is only shown when there is nothing still burning.
_FIRE_TYPES = ("FIRE_DETECTED", "SMOKE_DETECTED", "FIRE_CLEARED")


def _handle_fire(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # Without this the plugin's events fell through to the "Analytics Update"
    # fallback and were dropped, so fire never appeared in the events feed.
    by_type = {}
    for event in e_data:
        etype = event.get("event_type")
        if etype in _FIRE_TYPES:
            by_type.setdefault(etype, event)

    for etype in _FIRE_TYPES:
        event = by_type.get(etype)
        if event is None:
            continue
        meta = event.get("metadata") or {}
        snap = _snap(meta)
        where = meta.get("zone_name")
        at = f" in {where}" if where else ""

        if etype == "FIRE_DETECTED":
            # Falls back to the cluster count for events written before zones
            # existed, so old rows keep rendering the way they always did.
            count = len(meta.get("fire_boxes") or [])
            plural = "" if count == 1 else "s"
            detail = at or f" ({count} cluster{plural})"
            return "danger", f"Fire Detected{detail}", snap
        if etype == "SMOKE_DETECTED":
            score = meta.get("score")
            conf = f" ({float(score):.0%} confidence)" if score is not None else ""
            return "warning", f"Smoke Detected{at}{conf}", snap
        if etype == "FIRE_CLEARED":
            kind = str(meta.get("kind") or "fire").title()
            secs = meta.get("duration_sec")
            ran = f" after {float(secs):.0f}s" if secs is not None else ""
            # "Fire" stays in the string on purpose: the notification sidebar
            # keys its icon off that word.
            return "success", f"Fire alert cleared — {kind}{at} ended{ran}", snap
    return None

def _handle_fight(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """
    SOW 2.7. The wording matters: this is an indication requiring human
    verification, and the feed is where a guard reads it, so it must not say
    "Fight Detected" as though the system knew.
    """
    for event in e_data:
        etype = event.get("event_type")
        if etype not in ("FIGHT_DETECTED", "FIGHT_CLEARED"):
            continue
        meta = event.get("metadata") or {}
        snap = _snap(meta)
        where = meta.get("zone_name")
        at = f" in {where}" if where else ""
        if etype == "FIGHT_DETECTED":
            score = meta.get("score")
            conf = f" ({float(score):.0%})" if score is not None else ""
            return ("danger",
                    f"Possible fight/quarrel{at}{conf} — verify before acting",
                    snap)
        secs = meta.get("duration_sec")
        ran = f" after {float(secs):.0f}s" if secs is not None else ""
        return "success", f"Fight/quarrel indication{at} ended{ran}", snap
    return None


def _handle_intrusion(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # Shares the restricted-zone vocabulary: both plugins now report the same
    # client-defined zones, so an operator should not have to learn that
    # "Zone Intrusion Detected" and "Yard Breach" are the same thing.
    for event in e_data:
        etype = event.get("event_type")
        if etype == "INTRUSION_DETECTED":
            meta = event.get("metadata") or {}
            colour, detail, snap = _zone_row(meta, "Breach")
            return colour, detail, snap or _snap(
                {"snapshot_file": event.get("snapshot_path")})
        if etype == "LOITERING_DETECTED":
            return _zone_row(event.get("metadata") or {}, "Loitering")
    return None

def _handle_attendance(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    for event in e_data:
        if event.get("event_type") in ["CHECK_IN", "CHECK_OUT"]:
            meta = event.get("metadata") or {}
            action = meta.get("action")
            emp = meta.get("employee_id")
            return ("success" if action == "CHECK IN" else "info",
                    f"Emp {emp} {action}", _snap(meta))
    return None

def _handle_people_counting(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    for event in e_data:
        if event.get("event_type") == "LINE_CROSSED":
            meta = event.get("metadata") or {}
            direction = meta.get("direction")
            if direction in ("IN", "OUT"):
                line_name = meta.get("line_name") or "counting line"
                severity = "success" if direction == "IN" else "info"
                # No running counters in the description: identical consecutive
                # crossings must dedup or they crowd every other event type
                # out of the 20-row per-camera feed.
                return severity, f"Person {direction} at {line_name}", _snap(meta)
            return "info", "Visitor detected in this camera", None
        elif event.get("event_type") == "PERSON_COUNT":
            count = event["metadata"].get("current_people_in_frame", 0)
            if count > 0:
                return "info", f"Person Count: {count}", None
    return None

def _handle_gesture(e_data: Dict, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    active_alerts = e_data.get("active_alerts", [])
    snapshot = "/" + e_data.get("snapshot_file") if e_data.get("snapshot_file") else None
    
    if "HAND_RAISE_DETECTED" in active_alerts:
        return "info", "Hand Raise Detected", snapshot
    elif "GESTURE_DETECTED" in active_alerts:
        gesture_events = e_data.get("gesture_events", [])
        if gesture_events:
            top_gesture = gesture_events[0].get("gesture", "Unknown")
            return "info", f"Gesture: {top_gesture}", snapshot
    return None

def _handle_visitor(e_data: Any, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # Handle both list and dict formats for backward compatibility
    events_list = e_data if isinstance(e_data, list) else (e_data["VisitorPlugin"] if isinstance(e_data, dict) and "VisitorPlugin" in e_data else [])
    
    for event in events_list:
        if isinstance(event, dict) and event.get("plugin_name") == "VisitorPlugin":
            evt_type = event.get("event_type")
            if evt_type in ["EMPLOYEE_RECOGNIZED", "VISITOR_RECOGNIZED", "UNKNOWN_PERSON"]:
                meta = event.get("metadata", {})
                vid = meta.get("visitor_id", "N/A")
                name = meta.get("name", "Unknown")
                snapshot = meta.get("snapshot_file")
                if snapshot:
                    snapshot = "/" + snapshot
                
                if evt_type == "EMPLOYEE_RECOGNIZED":
                    dept = "Broker 1" if hash(vid) % 2 == 0 else "Broker 2"
                    role = f"Employee [{dept}]"
                    event_type_str = "success"
                elif evt_type == "VISITOR_RECOGNIZED":
                    role = "Visitor"
                    event_type_str = "info"
                else:
                    role = "Unknown"
                    event_type_str = "warning"
                    
                action_word = "Checkout" if "CHECK OUT" in cam_name.upper() else "Detect"
                return event_type_str, f"{role} {action_word} with Camera {cam_name} ID: {vid} Name: {name}", snapshot
    return None

def _handle_anpr(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # A list hit outranks the plain read of the same plate: the row that
    # reaches the operator should say the vehicle is barred, not merely that
    # a plate was seen.
    for event in e_data:
        etype = event.get("event_type")
        if etype not in ("BLACKLIST_MATCH", "WHITELIST_MATCH"):
            continue
        meta = event.get("metadata") or {}
        plate = meta.get("plate_number", "?")
        listed = meta.get("listed_plate")
        kind = meta.get("match_kind")
        # Say when the match was approximate — an operator acting on a hit
        # needs to know whether the read was exact or reconstructed.
        qualifier = "" if kind in (None, "exact") else f" (~{listed})"
        if etype == "BLACKLIST_MATCH":
            reason = meta.get("list_reason")
            return ("danger",
                    f"BLACKLISTED plate {plate}{qualifier}"
                    + (f": {reason}" if reason else ""),
                    _snap(meta))
        return ("success",
                f"Authorised plate {plate}{qualifier}"
                + (f" [{meta.get('list_type')}]" if meta.get("list_type") else ""),
                _snap(meta))

    for event in e_data:
        if event.get("event_type") == "NEW_PLATE":
            metadata = event.get("metadata", {})
            plate_num = metadata.get("plate_number")
            snap = metadata.get("vehicle_snapshot")
            if snap:
                snap = "/" + snap
            if plate_num:
                return "info", f"Plate Detected: {plate_num}", snap
        elif event.get("event_type") == "LIVE_TRACKING":
            metadata = event.get("metadata", {})
            plate_num = metadata.get("plate_number")
            if plate_num:
                return "info", f"Plate Detected: {plate_num}", None
    return None

def _handle_parking(e_data: list, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    if isinstance(e_data, list):
        for event in e_data:
            if event.get("event_type") == "PARKING_ALERT":
                meta = event.get("metadata", {})
                bay = meta.get("bay_id", "Unknown")
                status = meta.get("status", "")
                return "danger" if status == "OCCUPIED" else "success", f"Parking Bay {bay} {status}", None
    return None

def _handle_ppe(e_data: Any, cam_name: str) -> Optional[Tuple[str, str, Optional[str]]]:
    # e_data could be a dict if wrapped by the pipeline, or a list of events
    events_list = e_data if isinstance(e_data, list) else (e_data["PPEDetectionPlugin"] if isinstance(e_data, dict) and "PPEDetectionPlugin" in e_data else [])
    
    for event in events_list:
        if isinstance(event, dict) and event.get("event_type") == "PPE_MISSING":
            metadata = event.get("metadata", {})
            snap = metadata.get("snapshot_file")
            if snap:
                snap = "/" + snap
            
            missing_count = len(metadata.get("persons_without_ppe", []))
            return "danger", f"Missing PPE Detected: {missing_count} Person(s)", snap
    return None

EVENT_DISPATCHER = {
    "EnterpriseSafetyPlugin": _handle_enterprise_safety,
    "FireDetectionPlugin": _handle_fire,
    "FightDetectionPlugin": _handle_fight,
    "IntrusionDetectionPlugin": _handle_intrusion,
    "AttendanceDetectionPlugin": _handle_attendance,
    "PeopleCountingPlugin": _handle_people_counting,
    "GestureDetectionPlugin": _handle_gesture,
    "ANPRPlugin": _handle_anpr,
    "ParkingAnalyticsPlugin": _handle_parking,
    "PPEDetectionPlugin": _handle_ppe,
    # These three had no handler, so their events were silently discarded by
    # the "Analytics Update" filter and never appeared in the feed.
    "RestrictionZonePlugin": _handle_restriction,
    "CartonCountingPlugin": _handle_carton,
    "VisitorPlugin": _handle_visitor_events,
    "FaceRecognitionPlugin": _handle_face,
}


def render_event_row(events, cam_name: str):
    """
    Renders every plugin present in one stored event row.

    A row is the whole `all_events` dict for a frame, so a camera running ten
    analytics writes ten plugins into a single row. Returns a list of
    (plugin_name, severity, description, snapshot_url) — one per plugin that
    produced something displayable, so no analytic is hidden behind another.
    """
    rendered = []
    if isinstance(events, dict):
        for plugin_name, handler in EVENT_DISPATCHER.items():
            if plugin_name not in events:
                continue
            try:
                res = handler(events[plugin_name], cam_name)
            except Exception:
                continue
            if res:
                rendered.append((plugin_name, res[0], res[1], res[2]))
    if not rendered:
        res = _handle_visitor(events, cam_name)
        if res:
            rendered.append(("VisitorPlugin", res[0], res[1], res[2]))
    return rendered

class EventService:
    @staticmethod
    def get_latest_events(
        camera_id: str = None, 
        start_date: str = None, 
        end_date: str = None, 
        severity: str = None, 
        category: str = None
    ):
        """Returns the latest historical events from the database."""
        from database.repositories.event_repository import EventRepository
        from database.repositories.camera_repository import CameraRepository
        db = SessionLocal()
        try:
            repo = EventRepository(db)
            repo_cam = CameraRepository(db)
            
            cameras = repo_cam.get_active_cameras()
            cam_map = {str(c.id): c.name for c in cameras}
            
            if camera_id:
                known_cameras = [(camera_id,)]
            else:
                known_cameras = repo.get_distinct_camera_ids()
                
            result = []
            
            for (cam_id,) in known_cameras:
                cam_events = repo.get_filtered_events(
                    camera_id=cam_id, 
                    start_date=start_date, 
                    end_date=end_date, 
                    limit=20
                )
                
                valid_cam_events = []
                # Consecutive-duplicate suppression is per plugin, not global:
                # with several analytics on one camera their rows interleave, so
                # a single `last_desc` would let a repeating plugin through
                # every time another plugin fired between its repeats.
                last_desc_by_plugin = {}
                for e in cam_events:
                    base_type = e.events.get("event_type", "info") if isinstance(e.events, dict) else "info"
                    base_desc = e.events.get("description", "Analytics Update") if isinstance(e.events, dict) else "Analytics Update"
                    base_snap = e.events.get("snapshot_file", None) if isinstance(e.events, dict) else None

                    cam_name = cam_map.get(e.camera_id, e.camera_id.split("/")[-1])

                    # One stored row carries EVERY plugin that fired on that
                    # frame. This loop used to break at the first handler that
                    # matched, so on a camera running ten analytics only the
                    # earliest plugin in EVENT_DISPATCHER order was ever
                    # visible and the other nine never reached the feed at all.
                    # Render each of them as its own entry.
                    rendered = render_event_row(e.events, cam_name)
                    if not rendered:
                        rendered = [(None, base_type, base_desc, base_snap)]

                    for plugin_name, event_type, description, snap in rendered:
                        snapshot_file = snap or base_snap

                        # Skip spammy analytics updates at the API level
                        if description == "Analytics Update":
                            continue

                        # Deduplicate consecutive identical events to prevent starvation
                        if description == last_desc_by_plugin.get(plugin_name):
                            continue
                        last_desc_by_plugin[plugin_name] = description

                        # Apply Category filter
                        event_category = "EVENT"
                        upper_desc = description.upper()
                        if "CHECK IN" in upper_desc or "CHECK OUT" in upper_desc or "ATTENDANCE" in upper_desc:
                            event_category = "ATTENDANCE"
                        elif "INTRUSION" in upper_desc:
                            event_category = "INTRUSION"
                        elif "FIRE" in upper_desc:
                            event_category = "SAFETY ALERT"
                        elif "PERSON COUNT" in upper_desc or "PEOPLE" in upper_desc:
                            event_category = "PEOPLE COUNT"

                        if category and category.upper() != event_category:
                            continue

                        # Apply Severity filter
                        if severity and severity.lower() != event_type:
                            continue

                        valid_cam_events.append({
                            # Several entries now come from one row, so the id
                            # must stay unique or the UI collapses them onto
                            # one React key.
                            "id": f"{e.id}:{plugin_name}" if plugin_name else e.id,
                            "timestamp": e.timestamp.isoformat(),
                            "camera_id": e.camera_id,
                            "camera_name": cam_name,
                            "plugin": plugin_name,
                            "event_type": event_type,
                            "description": description,
                            "snapshot_file": snapshot_file
                        })

                    if len(valid_cam_events) >= 15:
                        break

                result.extend(valid_cam_events)

            result.sort(key=lambda x: x["timestamp"], reverse=True)
            return result
        finally:
            db.close()

    @staticmethod
    def get_dashboard_stats(active_cameras_count: int):
        import psutil
        from database.repositories.event_repository import EventRepository
        from database.repositories.camera_repository import CameraRepository
        db = SessionLocal()
        critical_alerts = 0
        total_cameras_db = 0
        total_people = 0
        workers = 0
        staff = 0
        visitors_count = 0
        vehicles_count = 0
        material_events_count = 0
        ppe_compliant_count = 0
        ppe_total_count = 0
        try:
            repo = EventRepository(db)
            cam_repo = CameraRepository(db)
            
            total_cameras_db = len(cam_repo.get_active_cameras() or [])
            
            # Fetch only the last 50 events to keep JSON parsing overhead <100ms
            events = db.query(CameraEvent).order_by(CameraEvent.timestamp.desc()).limit(50).all()
            for e in events:
                if isinstance(e.events, dict):
                    if "EnterpriseSafetyPlugin" in e.events:
                        active = e.events["EnterpriseSafetyPlugin"].get("active_alerts", [])
                        if "FIRE_DETECTED" in active:
                            critical_alerts += 1
                    if "FireDetectionPlugin" in e.events:
                        critical_alerts += len(e.events["FireDetectionPlugin"])
                    if "FightDetectionPlugin" in e.events:
                        critical_alerts += len(e.events["FightDetectionPlugin"])
                    if "IntrusionDetectionPlugin" in e.events:
                        critical_alerts += len(e.events["IntrusionDetectionPlugin"])
                    if "PeopleCountingPlugin" in e.events:
                        for pe in e.events["PeopleCountingPlugin"]:
                            if isinstance(pe, dict) and "count" in pe:
                                total_people = max(total_people, pe.get("count", 0))
                    if "ANPRPlugin" in e.events:
                        vehicles_count += len(e.events["ANPRPlugin"])
                    if "CartonCountingPlugin" in e.events:
                        material_events_count += len(e.events["CartonCountingPlugin"])
                    if "PPEDetectionPlugin" in e.events:
                        for ppe_e in e.events["PPEDetectionPlugin"]:
                            if isinstance(ppe_e, dict):
                                meta = ppe_e.get("metadata", {})
                                missing = len(meta.get("persons_without_ppe", []))
                                if missing > 0:
                                    ppe_total_count += missing
                                else:
                                    ppe_compliant_count += 1
                                    ppe_total_count += 1
        finally:
            db.close()

        cpu_usage = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        net_mbps = round((net.bytes_sent + net.bytes_recv) / (1024 * 1024), 1)

        safety_score = 0
        if total_cameras_db > 0:
            safety_score = max(0, 100 - (critical_alerts * 10))

        ppe_compliance = 0
        if ppe_total_count > 0:
            ppe_compliance = round((ppe_compliant_count / ppe_total_count) * 100)
        elif total_cameras_db > 0:
            ppe_compliance = 100

        return {
            "total_cameras": total_cameras_db,
            "ai_enabled": total_cameras_db,
            "critical_alerts": critical_alerts,
            "uptime": "99.9%",
            "system_health": {
                "cpu_usage": round(cpu_usage, 1),
                "gpu_usage": 0,
                "ram_usage": round(ram.percent, 1),
                "storage_usage": round(disk.percent, 1),
                "network_bandwidth": net_mbps
            },
            "online_cameras": active_cameras_count or 0,
            "offline_cameras": max(0, total_cameras_db - (active_cameras_count or 0)),
            "people_on_site": {
                "total": total_people,
                "workers": workers,
                "staff": staff,
                "visitors": visitors_count
            },
            "safety_score": safety_score,
            "ppe_compliance": ppe_compliance,
            "vehicles_inside": vehicles_count,
            "material_events": material_events_count
        }
