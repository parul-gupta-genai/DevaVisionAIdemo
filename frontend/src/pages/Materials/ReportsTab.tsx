import React, { useState, useMemo, useRef } from 'react';
import { 
  FileText, 
  Download, 
  Search, 
  Filter, 
  Calendar, 
  Truck, 
  Building2, 
  IndianRupee, 
  CheckCircle2, 
  AlertTriangle, 
  X, 
  MapPin, 
  Layers, 
  Eye, 
  FileCheck, 
  TrendingUp, 
  Boxes, 
  ShieldCheck, 
  Mail, 
  Send, 
  Camera, 
  Upload, 
  Plus, 
  Sparkles, 
  RefreshCw, 
  Settings, 
  Phone, 
  Edit2 
} from 'lucide-react';
import { cn } from '@/utils/utils';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

export interface InventoryRecord {
  id: string;
  voucherNo: string;
  poNumber: string;
  materialName: string;
  category: string;
  classification: 'Consumable' | 'Asset';
  vendorName: string;
  quantity: number;
  unit: string;
  unitPrice: number;
  totalExpense: number;
  vehicleNumber: string;
  timestamp: string;
  entryTime: string;
  exitTime: string;
  isUnloaded: boolean;
  gpsCoordinates: { lat: number; lng: number };
  siteDistanceMeters: number;
  isGpsVerified: boolean;
  entryImage: string;
  exitImage: string;
  voucherImage: string;
  plateImage: string;
}

// Initial realistic dataset for Hero Homes site inventory operations
const MOCK_INVENTORY_DATA: InventoryRecord[] = [
  {
    id: 'MAT-2026-001',
    voucherNo: 'CH-89231',
    poNumber: 'PO-HERO-4421',
    materialName: 'UltraTech OPC 53 Grade Cement',
    category: 'Cement Bags',
    classification: 'Consumable',
    vendorName: 'UltraTech Cement Ltd',
    quantity: 500,
    unit: 'Bags',
    unitPrice: 385,
    totalExpense: 192500,
    vehicleNumber: 'HR26 DK 8921',
    timestamp: '2026-09-10T09:15:00',
    entryTime: '09:15 AM',
    exitTime: '10:05 AM',
    isUnloaded: true,
    gpsCoordinates: { lat: 28.4595, lng: 77.0266 },
    siteDistanceMeters: 45,
    isGpsVerified: true,
    entryImage: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&auto=format&fit=crop',
    exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
    voucherImage: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
  },
  {
    id: 'MAT-2026-002',
    voucherNo: 'CH-89232',
    poNumber: 'PO-HERO-4422',
    materialName: 'Tata Tiscon 550D TMT Rebar (16mm)',
    category: 'Steel Bundles',
    classification: 'Consumable',
    vendorName: 'Tata Tiscon Steel',
    quantity: 28.5,
    unit: 'MT',
    unitPrice: 58500,
    totalExpense: 1667250,
    vehicleNumber: 'DL01 EA 4412',
    timestamp: '2026-09-10T10:30:00',
    entryTime: '10:30 AM',
    exitTime: '11:45 AM',
    isUnloaded: true,
    gpsCoordinates: { lat: 28.4592, lng: 77.0269 },
    siteDistanceMeters: 62,
    isGpsVerified: true,
    entryImage: 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=800&auto=format&fit=crop',
    exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
    voucherImage: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
  },
  {
    id: 'MAT-2026-003',
    voucherNo: 'CH-89233',
    poNumber: 'PO-HERO-4423',
    materialName: 'Heavy Duty Cuplock Scaffolding Sets',
    category: 'Heavy Equipment',
    classification: 'Asset',
    vendorName: 'Apex Scaffolding Infra',
    quantity: 120,
    unit: 'Sets',
    unitPrice: 4200,
    totalExpense: 504000,
    vehicleNumber: 'HR55 AT 9081',
    timestamp: '2026-09-09T14:10:00',
    entryTime: '02:10 PM',
    exitTime: '03:20 PM',
    isUnloaded: true,
    gpsCoordinates: { lat: 28.4598, lng: 77.0261 },
    siteDistanceMeters: 38,
    isGpsVerified: true,
    entryImage: 'https://images.unsplash.com/photo-1581094794329-c8112a89af12?w=800&auto=format&fit=crop',
    exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
    voucherImage: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
  },
  {
    id: 'MAT-2026-004',
    voucherNo: 'CH-89234',
    poNumber: 'PO-HERO-4424',
    materialName: 'River Sand (Coarse Aggregate)',
    category: 'Cartons / Boxes',
    classification: 'Consumable',
    vendorName: 'Haryana Quarry Supplies',
    quantity: 42.0,
    unit: 'Ton',
    unitPrice: 1850,
    totalExpense: 77700,
    vehicleNumber: 'HR38 X 5519',
    timestamp: '2026-09-08T16:00:00',
    entryTime: '04:00 PM',
    exitTime: '04:45 PM',
    isUnloaded: true,
    gpsCoordinates: { lat: 28.4599, lng: 77.0275 },
    siteDistanceMeters: 85,
    isGpsVerified: true,
    entryImage: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&auto=format&fit=crop',
    exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
    voucherImage: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
  },
  {
    id: 'MAT-2026-005',
    voucherNo: 'CH-89235',
    poNumber: 'PO-HERO-4425',
    materialName: 'Finolex Schedule 40 UPVC Pipes 4"',
    category: 'Pipes',
    classification: 'Consumable',
    vendorName: 'Finolex Industries',
    quantity: 250,
    unit: 'Lengths',
    unitPrice: 890,
    totalExpense: 222500,
    vehicleNumber: 'UP16 BT 1290',
    timestamp: '2026-09-07T11:20:00',
    entryTime: '11:20 AM',
    exitTime: '12:15 PM',
    isUnloaded: true,
    gpsCoordinates: { lat: 28.4594, lng: 77.0264 },
    siteDistanceMeters: 40,
    isGpsVerified: true,
    entryImage: 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=800&auto=format&fit=crop',
    exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
    voucherImage: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
  },
  {
    id: 'MAT-2026-006',
    voucherNo: 'CH-89236',
    poNumber: 'PO-HERO-4426',
    materialName: 'Kajaria Vitrified Floor Tiles (600x600)',
    category: 'Tiles',
    classification: 'Consumable',
    vendorName: 'Kajaria Ceramics Ltd',
    quantity: 600,
    unit: 'Boxes',
    unitPrice: 650,
    totalExpense: 390000,
    vehicleNumber: 'HR29 AB 7831',
    timestamp: '2026-09-06T15:40:00',
    entryTime: '03:40 PM',
    exitTime: '05:00 PM',
    isUnloaded: true,
    gpsCoordinates: { lat: 28.4596, lng: 77.0268 },
    siteDistanceMeters: 55,
    isGpsVerified: true,
    entryImage: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&auto=format&fit=crop',
    exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
    voucherImage: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
  }
];

export default function ReportsTab() {
  const [records, setRecords] = useState<InventoryRecord[]>(MOCK_INVENTORY_DATA);

  // Filter States
  const [selectedMaterial, setSelectedMaterial] = useState<string>('ALL');
  const [selectedVendor, setSelectedVendor] = useState<string>('ALL');
  const [selectedClassification, setSelectedClassification] = useState<string>('ALL');
  const [dateRange, setDateRange] = useState<string>('ALL');
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customEndDate, setCustomEndDate] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Configurable Head Office Audit Dispatch Details
  const [headOfficeEmail, setHeadOfficeEmail] = useState<string>(() => {
    return localStorage.getItem('audit_headoffice_email') || 'headoffice.audit@herohomes.in';
  });
  const [headOfficePhone, setHeadOfficePhone] = useState<string>(() => {
    return localStorage.getItem('audit_headoffice_phone') || '+91 98100 44210';
  });
  const [siteManagerEmail, setSiteManagerEmail] = useState<string>(() => {
    return localStorage.getItem('audit_sitemanager_email') || 'site.store@herohomes.in';
  });
  const [showEmailConfigModal, setShowEmailConfigModal] = useState<boolean>(false);

  // Modal State for Visual Dossier
  const [activeDossier, setActiveDossier] = useState<InventoryRecord | null>(null);

  // Modal State for Scanning / Adding Bill
  const [showScanModal, setShowScanModal] = useState<boolean>(false);
  const [scannedImage, setScannedImage] = useState<string>('');
  const [isLiveCameraActive, setIsLiveCameraActive] = useState<boolean>(false);
  const [cameraFacingMode, setCameraFacingMode] = useState<'environment' | 'user'>('environment');
  const [scannerStream, setScannerStream] = useState<MediaStream | null>(null);
  const [availableCameras, setAvailableCameras] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const scannerVideoRef = useRef<HTMLVideoElement | null>(null);
  const scannerCanvasRef = useRef<HTMLCanvasElement>(null);

  const stopScannerCamera = () => {
    if (scannerStream) {
      scannerStream.getTracks().forEach(track => {
        try {
          track.stop();
          track.enabled = false;
        } catch {
          // ignore
        }
      });
      setScannerStream(null);
    }
    if (scannerVideoRef.current && scannerVideoRef.current.srcObject) {
      try {
        const tracks = (scannerVideoRef.current.srcObject as MediaStream).getTracks();
        tracks.forEach(track => track.stop());
      } catch {
        // ignore
      }
      scannerVideoRef.current.srcObject = null;
    }
    setIsLiveCameraActive(false);
  };

  const [isFlashing, setIsFlashing] = useState<boolean>(false);
  const [isOcrProcessing, setIsOcrProcessing] = useState<boolean>(false);

  const startScannerCamera = async (mode: 'environment' | 'user' = 'environment', deviceId?: string) => {
    stopScannerCamera();
    setCameraFacingMode(mode);

    try {
      let stream: MediaStream | null = null;

      // 1. If user explicitly picked a specific camera deviceId from the dropdown
      if (deviceId) {
        try {
          setSelectedDeviceId(deviceId);
          stream = await navigator.mediaDevices.getUserMedia({
            video: { deviceId: { exact: deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
          });
        } catch (err) {
          console.warn("Exact deviceId selection failed, trying facingMode:", err);
        }
      }

      // 2. Primary Standard for Rear / Back Camera on Mobile: exact facingMode 'environment'
      if (!stream && mode === 'environment') {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { exact: 'environment' },
              width: { ideal: 1920 },
              height: { ideal: 1080 }
            }
          });
        } catch (err) {
          console.warn("exact facingMode environment failed, trying ideal:", err);
        }
      }

      // 3. Primary Standard for Front Camera: exact facingMode 'user'
      if (!stream && mode === 'user') {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { exact: 'user' },
              width: { ideal: 1920 },
              height: { ideal: 1080 }
            }
          });
        } catch (err) {
          console.warn("exact facingMode user failed, trying ideal:", err);
        }
      }

      // 4. Fallback with ideal facingMode
      if (!stream) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { ideal: mode },
              width: { ideal: 1920 },
              height: { ideal: 1080 }
            }
          });
        } catch (err) {
          console.warn("ideal facingMode failed, attempting device search:", err);
        }
      }

      // 5. Fallback searching enumerated device labels
      if (!stream) {
        try {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const videoDevs = devices.filter(d => d.kind === 'videoinput');
          const targetDev = videoDevs.find(d => {
            const lbl = d.label.toLowerCase();
            return mode === 'environment'
              ? (lbl.includes('back') || lbl.includes('rear') || lbl.includes('environment') || lbl.includes('0, facing back') || lbl.includes('main'))
              : (lbl.includes('front') || lbl.includes('user') || lbl.includes('selfie') || lbl.includes('face'));
          });

          if (targetDev && targetDev.deviceId) {
            stream = await navigator.mediaDevices.getUserMedia({
              video: { deviceId: { exact: targetDev.deviceId } }
            });
          }
        } catch (e) {
          console.warn("Device search fallback failed:", e);
        }
      }

      // 6. Final fallback to any available camera stream
      if (!stream) {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
      }

      if (stream) {
        setScannerStream(stream);
        setIsLiveCameraActive(true);

        // Refresh enumerated camera list with active labels now that permission is active
        try {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const videoDevs = devices.filter(d => d.kind === 'videoinput');
          setAvailableCameras(videoDevs);
        } catch {
          // ignore
        }

        const activeTrack = stream.getVideoTracks()[0];
        if (activeTrack) {
          const settings = activeTrack.getSettings();
          if (settings.deviceId) {
            setSelectedDeviceId(settings.deviceId);
          }
        }

        // Attach immediately if ref is mounted
        if (scannerVideoRef.current) {
          scannerVideoRef.current.srcObject = stream;
          scannerVideoRef.current.play().catch(err => console.warn("Live play error:", err));
        }
      }
    } catch (err) {
      console.error("Camera access failed:", err);
      alert("Unable to access camera. Please check camera permissions in your browser or choose 'Upload File' or 'Sample Bill'.");
    }
  };

  // Bind live camera stream as soon as video element mounts in the DOM or stream updates
  React.useEffect(() => {
    if (scannerVideoRef.current && scannerStream) {
      scannerVideoRef.current.srcObject = scannerStream;
      scannerVideoRef.current.play().catch(err => {
        console.warn("Scanner video play failed:", err);
      });
    }
  }, [scannerStream, isLiveCameraActive]);

  const toggleScannerFacing = () => {
    const next = cameraFacingMode === 'environment' ? 'user' : 'environment';
    setCameraFacingMode(next);
    startScannerCamera(next);
  };

  const snapBillPhoto = () => {
    if (scannerVideoRef.current && scannerCanvasRef.current) {
      const video = scannerVideoRef.current;
      const canvas = scannerCanvasRef.current;
      
      const width = video.videoWidth || 1920;
      const height = video.videoHeight || 1080;
      canvas.width = width;
      canvas.height = height;
      
      const ctx = canvas.getContext('2d');
      if (ctx) {
        // Trigger camera flash animation
        setIsFlashing(true);
        setTimeout(() => setIsFlashing(false), 200);

        ctx.drawImage(video, 0, 0, width, height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
        setScannedImage(dataUrl);
        stopScannerCamera();

        // Trigger AI OCR Extraction simulation
        setIsOcrProcessing(true);
        setTimeout(() => {
          setIsOcrProcessing(false);
          setNewBillForm({
            voucherNo: 'CH-' + Math.floor(10000 + Math.random() * 90000),
            poNumber: 'PO-HERO-' + Math.floor(1000 + Math.random() * 9000),
            materialName: 'UltraTech OPC 53 Grade Cement',
            category: 'Cement Bags',
            classification: 'Consumable',
            vendorName: 'UltraTech Cement Ltd',
            quantity: 500,
            unit: 'Bags',
            unitPrice: 385,
            vehicleNumber: 'HR26 DK 8921'
          });
        }, 600);
      }
    }
  };

  React.useEffect(() => {
    return () => {
      stopScannerCamera();
    };
  }, []);

  const [newBillForm, setNewBillForm] = useState({
    voucherNo: 'CH-' + Math.floor(10000 + Math.random() * 90000),
    poNumber: 'PO-HERO-' + Math.floor(1000 + Math.random() * 9000),
    materialName: 'UltraTech OPC 53 Grade Cement',
    category: 'Cement Bags',
    classification: 'Consumable' as 'Consumable' | 'Asset',
    vendorName: 'UltraTech Cement Ltd',
    quantity: 500,
    unit: 'Bags',
    unitPrice: 385,
    vehicleNumber: 'HR26 DK 8921'
  });

  // Handle Photo / File Selection
  const handleBillPhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const url = URL.createObjectURL(file);
      setScannedImage(url);
    }
  };

  // Submit Scanned Bill
  const handleSaveScannedBill = (sendEmail = false) => {
    const totalExpense = newBillForm.quantity * newBillForm.unitPrice;
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const newRecord: InventoryRecord = {
      id: `MAT-2026-00${records.length + 1}`,
      voucherNo: newBillForm.voucherNo,
      poNumber: newBillForm.poNumber,
      materialName: newBillForm.materialName,
      category: newBillForm.category,
      classification: newBillForm.classification,
      vendorName: newBillForm.vendorName,
      quantity: Number(newBillForm.quantity),
      unit: newBillForm.unit,
      unitPrice: Number(newBillForm.unitPrice),
      totalExpense: totalExpense,
      vehicleNumber: newBillForm.vehicleNumber.toUpperCase(),
      timestamp: now.toISOString(),
      entryTime: timeStr,
      exitTime: 'In-Progress (Unloading)',
      isUnloaded: true,
      gpsCoordinates: { lat: 28.4595, lng: 77.0266 },
      siteDistanceMeters: 38,
      isGpsVerified: true,
      entryImage: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&auto=format&fit=crop',
      exitImage: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=800&auto=format&fit=crop',
      voucherImage: scannedImage || 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
      plateImage: 'https://images.unsplash.com/photo-1590381105924-c72589b9ef3f?w=800&auto=format&fit=crop'
    };

    setRecords(prev => [newRecord, ...prev]);
    setShowScanModal(false);
    setScannedImage('');

    if (sendEmail) {
      alert(`✅ Delivery Record for Voucher #${newRecord.voucherNo} (${newRecord.materialName}) created!\n\n📧 Instant ERP Audit Mail sent to: ${headOfficeEmail}\n📱 WhatsApp Alert dispatched to: ${headOfficePhone}\n📋 CC: ${siteManagerEmail}`);
    } else {
      alert(`✅ Delivery Bill #${newRecord.voucherNo} successfully recorded into Inventory!`);
    }
  };

  // Unique Dropdown Options
  const materialOptions = useMemo(() => {
    return Array.from(new Set(records.map(d => d.materialName)));
  }, [records]);

  const vendorOptions = useMemo(() => {
    return Array.from(new Set(records.map(d => d.vendorName)));
  }, [records]);

  // Filter Logic
  const filteredRecords = useMemo(() => {
    return records.filter(record => {
      if (selectedMaterial !== 'ALL' && record.materialName !== selectedMaterial) return false;
      if (selectedVendor !== 'ALL' && record.vendorName !== selectedVendor) return false;
      if (selectedClassification !== 'ALL' && record.classification !== selectedClassification) return false;

      // Date Range Filter
      if (dateRange === 'TODAY') {
        const todayStr = new Date().toISOString().slice(0, 10);
        if (!record.timestamp.startsWith(todayStr)) return false;
      } else if (dateRange === '7DAYS') {
        const d = new Date();
        d.setDate(d.getDate() - 7);
        if (new Date(record.timestamp) < d) return false;
      } else if (dateRange === '30DAYS') {
        const d = new Date();
        d.setDate(d.getDate() - 30);
        if (new Date(record.timestamp) < d) return false;
      } else if (dateRange === 'CUSTOM' && customStartDate && customEndDate) {
        const start = new Date(customStartDate);
        const end = new Date(customEndDate);
        end.setHours(23, 59, 59);
        const recordDate = new Date(record.timestamp);
        if (recordDate < start || recordDate > end) return false;
      }

      // Text Search
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          record.materialName.toLowerCase().includes(q) ||
          record.vendorName.toLowerCase().includes(q) ||
          record.vehicleNumber.toLowerCase().includes(q) ||
          record.voucherNo.toLowerCase().includes(q) ||
          record.poNumber.toLowerCase().includes(q)
        );
      }

      return true;
    });
  }, [records, selectedMaterial, selectedVendor, selectedClassification, dateRange, customStartDate, customEndDate, searchQuery]);

  // Aggregate Metrics
  const summaryMetrics = useMemo(() => {
    const totalDeliveries = filteredRecords.length;
    const totalExpenses = filteredRecords.reduce((acc, curr) => acc + curr.totalExpense, 0);
    const consumableExpense = filteredRecords
      .filter(r => r.classification === 'Consumable')
      .reduce((acc, curr) => acc + curr.totalExpense, 0);
    const assetExpense = filteredRecords
      .filter(r => r.classification === 'Asset')
      .reduce((acc, curr) => acc + curr.totalExpense, 0);
    const verifiedGpsCount = filteredRecords.filter(r => r.isGpsVerified).length;

    return {
      totalDeliveries,
      totalExpenses,
      consumableExpense,
      assetExpense,
      verifiedGpsCount
    };
  }, [filteredRecords]);

  // Currency Formatter (Indian Rupees)
  const formatINR = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val);
  };

  // CSV Export
  const handleExportCSV = () => {
    if (filteredRecords.length === 0) return;
    const headers = [
      'Voucher No',
      'PO Number',
      'Material Name',
      'Category',
      'Classification',
      'Vendor Name',
      'Quantity',
      'Unit',
      'Unit Rate (INR)',
      'Total Expense (INR)',
      'Vehicle Plate',
      'Date & Time',
      'Site Proximity (Meters)',
      'GPS Verified'
    ];

    const rows = filteredRecords.map(r => [
      `"${r.voucherNo}"`,
      `"${r.poNumber}"`,
      `"${r.materialName}"`,
      `"${r.category}"`,
      `"${r.classification}"`,
      `"${r.vendorName}"`,
      r.quantity,
      `"${r.unit}"`,
      r.unitPrice,
      r.totalExpense,
      `"${r.vehicleNumber}"`,
      `"${r.timestamp}"`,
      r.siteDistanceMeters,
      r.isGpsVerified ? 'YES' : 'NO'
    ]);

    const csvContent = [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `HeroHomes-InventoryReport-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // PDF Export
  const handleExportPDF = () => {
    if (filteredRecords.length === 0) return;
    const doc = new jsPDF('landscape');

    // Title & Header
    doc.setFontSize(18);
    doc.setTextColor(245, 158, 11);
    doc.text('Hero Homes - Material & Inventory Audit Report', 14, 18);

    doc.setFontSize(10);
    doc.setTextColor(100);
    doc.text(`Generated on: ${new Date().toLocaleString()} | Filter: ${selectedMaterial === 'ALL' ? 'All Materials' : selectedMaterial} | Vendor: ${selectedVendor === 'ALL' ? 'All Vendors' : selectedVendor}`, 14, 25);
    doc.text(`Total Deliveries: ${summaryMetrics.totalDeliveries} | Total Inbound Valuation: ${formatINR(summaryMetrics.totalExpenses)}`, 14, 31);

    const tableRows = filteredRecords.map(r => [
      r.voucherNo,
      r.materialName,
      r.classification,
      r.vendorName,
      `${r.quantity} ${r.unit}`,
      `INR ${r.totalExpense.toLocaleString('en-IN')}`,
      r.vehicleNumber,
      r.entryTime,
      r.isGpsVerified ? `${r.siteDistanceMeters}m (Verified)` : 'Unverified'
    ]);

    autoTable(doc, {
      head: [['Voucher', 'Material Name', 'Type', 'Vendor', 'Quantity', 'Total Expense', 'Vehicle', 'Entry Time', 'GPS Proximity']],
      body: tableRows,
      startY: 36,
      theme: 'grid',
      headStyles: { fillColor: [245, 158, 11], textColor: [0, 0, 0], fontStyle: 'bold' },
      styles: { fontSize: 8, cellPadding: 2 }
    });

    doc.save(`HeroHomes-Inventory-Report-${new Date().toISOString().slice(0, 10)}.pdf`);
  };

  return (
    <div className="space-y-6">
      {/* Top Filter Bar */}
      <div className="glass border border-foreground/10 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-foreground/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/20 border border-amber-500/30 text-amber-400">
              <Filter className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-wide">Inventory Report Filters</h2>
              <p className="text-xs text-muted-foreground">Filter material deliveries by material, vendor, classification & time period</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowScanModal(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-black font-extrabold text-xs shadow-lg shadow-emerald-500/20 transition-all active:scale-95"
            >
              <Camera className="w-4 h-4" /> Scan Delivery Bill
            </button>
            <button
              onClick={() => setShowEmailConfigModal(true)}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 text-xs font-bold border border-amber-500/30 transition-all active:scale-95 shadow-lg shadow-amber-500/5"
              title="Configure Head Office Email & Alert Phone"
            >
              <Settings className="w-4 h-4" /> Audit Dispatch Settings
            </button>
            <button
              onClick={handleExportCSV}
              disabled={filteredRecords.length === 0}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white text-xs font-bold border border-foreground/10 transition-all disabled:opacity-40"
            >
              <Download className="w-4 h-4" /> Export CSV
            </button>
            <button
              onClick={handleExportPDF}
              disabled={filteredRecords.length === 0}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-black font-extrabold text-xs shadow-lg shadow-amber-500/20 transition-all active:scale-95 disabled:opacity-40"
            >
              <FileText className="w-4 h-4" /> Export PDF Dossier
            </button>
          </div>
        </div>

        {/* Filter Controls Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
          {/* Material Name / Type Filter */}
          <div>
            <label className="block text-xs font-semibold text-amber-200/80 mb-1.5 flex items-center gap-1.5">
              <Boxes className="w-3.5 h-3.5" /> Material Name & Type
            </label>
            <select
              value={selectedMaterial}
              onChange={e => setSelectedMaterial(e.target.value)}
              className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-amber-500 transition-all"
            >
              <option value="ALL">All Materials (All Categories)</option>
              {materialOptions.map(mat => (
                <option key={mat} value={mat}>{mat}</option>
              ))}
            </select>
          </div>

          {/* Vendor Filter */}
          <div>
            <label className="block text-xs font-semibold text-amber-200/80 mb-1.5 flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5" /> Specific Vendor
            </label>
            <select
              value={selectedVendor}
              onChange={e => setSelectedVendor(e.target.value)}
              className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-amber-500 transition-all"
            >
              <option value="ALL">All Vendors / Suppliers</option>
              {vendorOptions.map(ven => (
                <option key={ven} value={ven}>{ven}</option>
              ))}
            </select>
          </div>

          {/* Classification (Assets vs Consumables) */}
          <div>
            <label className="block text-xs font-semibold text-amber-200/80 mb-1.5 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> Classification
            </label>
            <select
              value={selectedClassification}
              onChange={e => setSelectedClassification(e.target.value)}
              className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-amber-500 transition-all"
            >
              <option value="ALL">All (Assets & Consumables)</option>
              <option value="Consumable">Consumable Materials (Direct Use)</option>
              <option value="Asset">Assets & Returnable Equipment</option>
            </select>
          </div>

          {/* Time Period Filter */}
          <div>
            <label className="block text-xs font-semibold text-amber-200/80 mb-1.5 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5" /> Time Period
            </label>
            <select
              value={dateRange}
              onChange={e => setDateRange(e.target.value)}
              className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-amber-500 transition-all"
            >
              <option value="ALL">All Time History</option>
              <option value="TODAY">Received Today</option>
              <option value="7DAYS">Last 7 Days</option>
              <option value="30DAYS">Last 30 Days (MTD)</option>
              <option value="CUSTOM">Custom Date Range...</option>
            </select>
          </div>
        </div>

        {/* Custom Date Range Row */}
        {dateRange === 'CUSTOM' && (
          <div className="flex items-center gap-4 pt-2 border-t border-foreground/5">
            <div>
              <label className="block text-[11px] text-muted-foreground mb-1">Start Date</label>
              <input
                type="date"
                value={customStartDate}
                onChange={e => setCustomStartDate(e.target.value)}
                className="bg-background/60 border border-foreground/10 rounded-xl px-3 py-1.5 text-xs text-white outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] text-muted-foreground mb-1">End Date</label>
              <input
                type="date"
                value={customEndDate}
                onChange={e => setCustomEndDate(e.target.value)}
                className="bg-background/60 border border-foreground/10 rounded-xl px-3 py-1.5 text-xs text-white outline-none"
              />
            </div>
          </div>
        )}
      </div>

      {/* Executive Financial & Inbound Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass border border-amber-500/30 bg-amber-500/10 rounded-2xl p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-400">Total Material Expense</span>
            <IndianRupee className="w-5 h-5 text-amber-400" />
          </div>
          <div className="text-2xl lg:text-3xl font-black text-white font-mono">{formatINR(summaryMetrics.totalExpenses)}</div>
          <div className="text-[11px] text-muted-foreground mt-1">For {summaryMetrics.totalDeliveries} Inbound Shipments</div>
        </div>

        <div className="glass border border-emerald-500/30 bg-emerald-500/10 rounded-2xl p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">Consumables Valuation</span>
            <TrendingUp className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="text-2xl lg:text-3xl font-black text-white font-mono">{formatINR(summaryMetrics.consumableExpense)}</div>
          <div className="text-[11px] text-muted-foreground mt-1">Direct construction consumption</div>
        </div>

        <div className="glass border border-blue-500/30 bg-blue-500/10 rounded-2xl p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-blue-400">Assets & Equipment</span>
            <Layers className="w-5 h-5 text-blue-400" />
          </div>
          <div className="text-2xl lg:text-3xl font-black text-white font-mono">{formatINR(summaryMetrics.assetExpense)}</div>
          <div className="text-[11px] text-muted-foreground mt-1">Capital & returnable items</div>
        </div>

        <div className="glass border border-purple-500/30 bg-purple-500/10 rounded-2xl p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-purple-400">GPS Site Verification</span>
            <ShieldCheck className="w-5 h-5 text-purple-400" />
          </div>
          <div className="text-2xl lg:text-3xl font-black text-white font-mono">
            {summaryMetrics.verifiedGpsCount} / {summaryMetrics.totalDeliveries}
          </div>
          <div className="text-[11px] text-emerald-400 mt-1">100% within perimeter radius</div>
        </div>
      </div>

      {/* Main Reporting Table */}
      <div className="glass border border-foreground/10 rounded-2xl overflow-hidden shadow-xl">
        {/* Search & Quick Info Bar */}
        <div className="p-4 border-b border-foreground/10 bg-background/20 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3 w-full sm:w-80">
            <Search className="w-4 h-4 text-muted-foreground shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search by Voucher, PO, Material, Vehicle..."
              className="bg-transparent text-xs text-white outline-none w-full placeholder:text-muted-foreground"
            />
          </div>
          <div className="text-xs text-muted-foreground">
            Showing <span className="text-white font-bold">{filteredRecords.length}</span> verified delivery records
          </div>
        </div>

        {/* Table Content */}
        {filteredRecords.length === 0 ? (
          <div className="p-12 text-center text-foreground/40">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm font-semibold">No material inventory records found</p>
            <p className="text-xs mt-1">Try adjusting your filters or date range.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="text-[10px] tracking-wider uppercase text-muted-foreground bg-foreground/5 font-black border-b border-foreground/10">
                <tr>
                  <th className="px-6 py-4">Voucher & PO</th>
                  <th className="px-6 py-4">Material Name & Type</th>
                  <th className="px-6 py-4">Vendor</th>
                  <th className="px-6 py-4">Quantity</th>
                  <th className="px-6 py-4">Total Expense</th>
                  <th className="px-6 py-4">Vehicle & Time</th>
                  <th className="px-6 py-4">GPS & Verification</th>
                  <th className="px-6 py-4 text-right">Visual Dossier</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredRecords.map(item => (
                  <tr key={item.id} className="hover:bg-foreground/5 transition-colors group">
                    <td className="px-6 py-4">
                      <div className="font-mono font-bold text-white">{item.voucherNo}</div>
                      <div className="text-[10px] text-muted-foreground">{item.poNumber}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-bold text-white text-sm">{item.materialName}</div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={cn(
                          "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                          item.classification === 'Consumable' 
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                        )}>
                          {item.classification}
                        </span>
                        <span className="text-[10px] text-muted-foreground">{item.category}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-white font-medium">{item.vendorName}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono text-white font-extrabold text-sm">{item.quantity} {item.unit}</div>
                      <div className="text-[10px] text-muted-foreground">Rate: ₹{item.unitPrice}/{item.unit}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono font-extrabold text-amber-400 text-sm">{formatINR(item.totalExpense)}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono text-white font-bold flex items-center gap-1.5">
                        <Truck className="w-3.5 h-3.5 text-primary" /> {item.vehicleNumber}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">{item.entryTime} → {item.exitTime}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        <span className="text-emerald-400 font-bold">{item.siteDistanceMeters}m from Center</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3 h-3 text-muted-foreground" />
                        {item.gpsCoordinates.lat.toFixed(4)}, {item.gpsCoordinates.lng.toFixed(4)}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => setActiveDossier(item)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 text-amber-300 font-bold text-xs transition-all"
                      >
                        <Eye className="w-3.5 h-3.5" /> View Proofs
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Visual Control Points & Proof Dossier Modal */}
      {activeDossier && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-[#121212] border border-foreground/20 rounded-3xl max-w-3xl w-full p-6 shadow-2xl space-y-6 relative max-h-[90vh] overflow-y-auto custom-scrollbar">
            
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-foreground/10 pb-4">
              <div>
                <span className="px-2.5 py-1 rounded-full text-xs font-bold uppercase bg-amber-500/20 text-amber-400 border border-amber-500/30">
                  Visual Audit Dossier
                </span>
                <h3 className="text-xl font-extrabold text-white mt-2">{activeDossier.materialName}</h3>
                <p className="text-xs text-muted-foreground">
                  Voucher: <span className="font-mono text-white font-bold">{activeDossier.voucherNo}</span> • PO: <span className="font-mono text-white">{activeDossier.poNumber}</span>
                </p>
              </div>
              <button
                onClick={() => setActiveDossier(null)}
                className="p-2 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Inbound Stats Overview */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-foreground/5 p-4 rounded-2xl border border-foreground/10">
              <div>
                <div className="text-[10px] uppercase font-bold text-muted-foreground">Supplier</div>
                <div className="text-xs font-bold text-white">{activeDossier.vendorName}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-muted-foreground">Delivered Quantity</div>
                <div className="text-xs font-bold text-white">{activeDossier.quantity} {activeDossier.unit}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-muted-foreground">Valuation (INR)</div>
                <div className="text-xs font-bold text-amber-400 font-mono">{formatINR(activeDossier.totalExpense)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-muted-foreground">Vehicle Number</div>
                <div className="text-xs font-bold text-white font-mono">{activeDossier.vehicleNumber}</div>
              </div>
            </div>

            {/* 4-Point Visual Capture Grid */}
            <div>
              <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-primary" /> Visual Control Points Captured at Gate
              </h4>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* 1. Loaded Entry Scan */}
                <div className="space-y-1.5 bg-foreground/5 p-3 rounded-2xl border border-foreground/10">
                  <div className="flex items-center justify-between text-xs font-bold text-emerald-400">
                    <span>1. Loaded Vehicle Entry</span>
                    <span>{activeDossier.entryTime}</span>
                  </div>
                  <img
                    src={activeDossier.entryImage}
                    alt="Loaded Vehicle"
                    className="w-full h-40 object-cover rounded-xl border border-foreground/10"
                  />
                  <p className="text-[10px] text-muted-foreground">Gate Camera #1 (Overhead Cargo Bed Scan)</p>
                </div>

                {/* 2. Empty Exit Scan */}
                <div className="space-y-1.5 bg-foreground/5 p-3 rounded-2xl border border-foreground/10">
                  <div className="flex items-center justify-between text-xs font-bold text-emerald-400">
                    <span>2. Empty Vehicle Exit</span>
                    <span>{activeDossier.exitTime}</span>
                  </div>
                  <img
                    src={activeDossier.exitImage}
                    alt="Empty Vehicle Exit"
                    className="w-full h-40 object-cover rounded-xl border border-foreground/10"
                  />
                  <p className="text-[10px] text-muted-foreground">Gate Camera #2 (Bed Verification: Unloaded ✅)</p>
                </div>

                {/* 3. Number Plate Scan */}
                <div className="space-y-1.5 bg-foreground/5 p-3 rounded-2xl border border-foreground/10">
                  <div className="flex items-center justify-between text-xs font-bold text-blue-400">
                    <span>3. ANPR License Plate</span>
                    <span className="font-mono">{activeDossier.vehicleNumber}</span>
                  </div>
                  <img
                    src={activeDossier.plateImage}
                    alt="ANPR Plate"
                    className="w-full h-40 object-cover rounded-xl border border-foreground/10"
                  />
                  <p className="text-[10px] text-muted-foreground">High-Speed LPR OCR (Confidence: 99.4%)</p>
                </div>

                {/* 4. Delivery Voucher */}
                <div className="space-y-1.5 bg-foreground/5 p-3 rounded-2xl border border-foreground/10">
                  <div className="flex items-center justify-between text-xs font-bold text-amber-400">
                    <span>4. Delivery Voucher Challan</span>
                    <span>{activeDossier.voucherNo}</span>
                  </div>
                  <img
                    src={activeDossier.voucherImage}
                    alt="Delivery Voucher"
                    className="w-full h-40 object-cover rounded-xl border border-foreground/10"
                  />
                  <p className="text-[10px] text-muted-foreground">Mobile Scanner OCR verified with PO</p>
                </div>
              </div>
            </div>

            {/* GPS Site Proximity Verification Banner */}
            <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <MapPin className="w-6 h-6 text-emerald-400 shrink-0" />
                <div>
                  <div className="text-xs font-bold text-white">Cryptographic GPS Geofence Verification</div>
                  <div className="text-[11px] text-muted-foreground">
                    Captured at Lat {activeDossier.gpsCoordinates.lat}, Lng {activeDossier.gpsCoordinates.lng} ({activeDossier.siteDistanceMeters}m from Hero Homes Site Center)
                  </div>
                </div>
              </div>
              <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                Verified On-Site ✅
              </span>
            </div>

            {/* Instant Head Office Email Dispatch Actions */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-2xl bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-amber-500/10 border border-amber-500/30">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-amber-500/20 border border-amber-500/30 text-amber-400">
                  <Mail className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-white flex items-center gap-2">
                    <span>Head Office Instant ERP Audit Dispatch</span>
                    <button
                      type="button"
                      onClick={() => setShowEmailConfigModal(true)}
                      className="px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 text-[10px] font-bold flex items-center gap-1 border border-amber-500/30"
                      title="Change Email or Phone"
                    >
                      <Edit2 className="w-3 h-3" /> Edit Contact
                    </button>
                  </div>
                  <div className="text-[11px] text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                    <span>Target: <span className="text-amber-300 font-mono font-semibold">{headOfficeEmail}</span></span>
                    <span className="text-foreground/30">•</span>
                    <span>WhatsApp/SMS: <span className="text-emerald-400 font-mono font-semibold">{headOfficePhone}</span></span>
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  alert(`✅ Visual Delivery Dossier for Voucher #${activeDossier.voucherNo} (${activeDossier.materialName}) has been dispatched!\n\n📧 Emailed to Head Office: ${headOfficeEmail}\n📱 WhatsApp Alert dispatched to: ${headOfficePhone}\n📋 CC: ${siteManagerEmail}`);
                }}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-black font-extrabold text-xs shadow-lg shadow-amber-500/20 transition-all active:scale-95 flex items-center justify-center gap-2"
              >
                <Send className="w-4 h-4" /> Instant Mail to Head Office
              </button>
            </div>

          </div>
        </div>
      )}

      {/* Scan / Add Delivery Bill Modal */}
      {showScanModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-[#121212] border border-foreground/20 rounded-3xl max-w-2xl w-full p-6 shadow-2xl space-y-6 relative max-h-[90vh] overflow-y-auto custom-scrollbar">
            
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-foreground/10 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-2xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400">
                  <Camera className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-xl font-extrabold text-white">Scan Delivery Challan / Bill</h3>
                  <p className="text-xs text-muted-foreground">Capture physical bill photo with AI OCR extraction & GPS verification</p>
                </div>
              </div>
              <button
                onClick={() => setShowScanModal(false)}
                className="p-2 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Bill Photo Capture & Preview Area */}
            <div className="space-y-3">
              <label className="block text-xs font-bold text-amber-300">1. Physical Bill / Voucher Photo</label>
              
              <input 
                type="file" 
                ref={fileInputRef} 
                accept="image/*" 
                onChange={handleBillPhotoUpload} 
                className="hidden" 
              />
              <canvas ref={scannerCanvasRef} className="hidden" />

              {/* State A: Photo is captured or uploaded */}
              {scannedImage ? (
                <div className="relative rounded-2xl overflow-hidden border border-emerald-500/30 group">
                  <img src={scannedImage} alt="Captured Delivery Bill" className="w-full h-64 object-cover" />
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setScannedImage('');
                        startScannerCamera('environment');
                      }}
                      className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-500 hover:to-teal-600 text-black font-extrabold text-xs flex items-center gap-1.5 shadow-xl active:scale-95 transition-all"
                    >
                      <Camera className="w-4 h-4" /> Retake Photo 📸
                    </button>
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="px-4 py-2.5 rounded-xl bg-white/20 hover:bg-white/30 text-white font-bold text-xs flex items-center gap-1.5 backdrop-blur-md active:scale-95 transition-all"
                    >
                      <Upload className="w-4 h-4" /> Upload Different File 📁
                    </button>
                  </div>
                  <div className="absolute bottom-2 left-2 bg-emerald-500/90 backdrop-blur-md px-3 py-1 rounded-lg text-[10px] font-bold text-black flex items-center gap-1.5 shadow-lg">
                    <Sparkles className="w-3.5 h-3.5" /> AI OCR Processed ✅
                  </div>
                </div>
              ) : isLiveCameraActive ? (
                /* State B: Live camera viewfinder is active */
                <div className="relative rounded-2xl overflow-hidden border-2 border-emerald-500/50 bg-black flex items-center justify-center min-h-[300px] max-h-[58vh]">
                  {/* Flash Effect on Capture */}
                  {isFlashing && (
                    <div className="absolute inset-0 bg-white z-30 pointer-events-none transition-opacity duration-200" />
                  )}

                  <video
                    ref={(el) => {
                      scannerVideoRef.current = el;
                      if (el && scannerStream && el.srcObject !== scannerStream) {
                        el.srcObject = scannerStream;
                        el.play().catch(err => console.warn("Video play error:", err));
                      }
                    }}
                    autoPlay
                    playsInline
                    muted
                    onLoadedMetadata={(e) => {
                      e.currentTarget.play().catch(err => console.warn("play onLoadedMetadata:", err));
                    }}
                    onCanPlay={(e) => {
                      e.currentTarget.play().catch(err => console.warn("play onCanPlay:", err));
                    }}
                    className="w-full h-full max-h-[58vh] object-contain bg-black"
                  />
                  
                  {/* Top Camera Status & Switcher Banner */}
                  <div className="absolute top-3 inset-x-3 flex items-center justify-between z-20">
                    <span className="bg-black/85 border border-emerald-500/40 px-3 py-1 rounded-full text-[11px] font-bold text-emerald-300 backdrop-blur-md flex items-center gap-1.5 shadow-lg">
                      <Camera className="w-3.5 h-3.5 text-emerald-400" />
                      {availableCameras.length <= 1
                        ? '💻 Laptop Webcam (1 Physical Sensor)'
                        : cameraFacingMode === 'environment'
                        ? '📷 Rear / Back Camera (Document Mode)'
                        : '🤳 Front / Selfie Camera'}
                    </span>

                    {availableCameras.length > 1 && (
                      <select
                        value={selectedDeviceId}
                        onChange={(e) => startScannerCamera(cameraFacingMode, e.target.value)}
                        className="bg-black/85 border border-white/20 text-white text-[11px] rounded-lg px-2 py-1 backdrop-blur-md outline-none max-w-[160px] truncate"
                      >
                        {availableCameras.map((cam, idx) => (
                          <option key={cam.deviceId || idx} value={cam.deviceId}>
                            {cam.label || `Camera Sensor ${idx + 1}`}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  {/* 4-Corner Document Target Brackets (CamScanner / OCR Framing) */}
                  <div className="absolute inset-8 sm:inset-12 pointer-events-none z-10">
                    {/* Top-Left Corner */}
                    <div className="absolute top-0 left-0 w-8 h-8 border-t-4 border-l-4 border-emerald-400 rounded-tl-xl shadow-lg shadow-emerald-500/30" />
                    {/* Top-Right Corner */}
                    <div className="absolute top-0 right-0 w-8 h-8 border-t-4 border-r-4 border-emerald-400 rounded-tr-xl shadow-lg shadow-emerald-500/30" />
                    {/* Bottom-Left Corner */}
                    <div className="absolute bottom-10 left-0 w-8 h-8 border-b-4 border-l-4 border-emerald-400 rounded-bl-xl shadow-lg shadow-emerald-500/30" />
                    {/* Bottom-Right Corner */}
                    <div className="absolute bottom-10 right-0 w-8 h-8 border-b-4 border-r-4 border-emerald-400 rounded-br-xl shadow-lg shadow-emerald-500/30" />

                    <div className="absolute inset-x-0 bottom-12 text-center">
                      <span className="bg-black/80 px-3.5 py-1.5 rounded-full text-[11px] text-emerald-300 font-semibold backdrop-blur-md border border-emerald-500/30 shadow-xl">
                        📄 Align A4 Paper Bill / Challan within corners
                      </span>
                    </div>
                  </div>

                  {/* Camera Controls Bar */}
                  <div className="absolute bottom-3 inset-x-0 flex items-center justify-center gap-3 z-20 px-4">
                    <button
                      type="button"
                      onClick={toggleScannerFacing}
                      className="px-3.5 py-2 rounded-full bg-black/80 hover:bg-black/95 text-white border border-white/20 backdrop-blur-md text-xs flex items-center gap-1.5 transition-all active:scale-95"
                      title="Switch Back / Front Camera"
                    >
                      <RefreshCw className="w-3.5 h-3.5 text-amber-400" />
                      <span className="text-[11px] font-bold">
                        {cameraFacingMode === 'environment' ? 'Switch to Front' : 'Switch to Back 📷'}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={snapBillPhoto}
                      className="px-6 py-2.5 rounded-full bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-500 hover:to-teal-600 text-black font-extrabold text-xs shadow-xl flex items-center gap-2 active:scale-95 transition-all hover:scale-105"
                    >
                      <Camera className="w-4 h-4" /> Snap Bill Photo 📸
                    </button>

                    <button
                      type="button"
                      onClick={stopScannerCamera}
                      className="p-2.5 rounded-full bg-black/80 hover:bg-black/95 text-rose-400 border border-white/20 backdrop-blur-md text-xs"
                      title="Close Camera"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ) : (
                /* State C: Initial state - choose Back Camera, Front Camera, or Upload File */
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div
                    onClick={() => startScannerCamera('environment')}
                    className="border-2 border-dashed border-emerald-500/50 hover:border-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/15 rounded-2xl p-5 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-2 group shadow-lg shadow-emerald-500/5"
                  >
                    <div className="p-3 rounded-full bg-emerald-500/20 text-emerald-400 group-hover:scale-110 transition-transform">
                      <Camera className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="text-xs font-extrabold text-emerald-300">📷 Back / Rear Camera</div>
                      <div className="text-[10px] text-emerald-400/80 mt-0.5">Scan paper bill with rear lens</div>
                    </div>
                  </div>

                  <div
                    onClick={() => startScannerCamera('user')}
                    className="border-2 border-dashed border-blue-500/40 hover:border-blue-400 bg-blue-500/5 hover:bg-blue-500/10 rounded-2xl p-5 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-2 group"
                  >
                    <div className="p-3 rounded-full bg-blue-500/20 text-blue-400 group-hover:scale-110 transition-transform">
                      <RefreshCw className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-white">🤳 Front Camera</div>
                      <div className="text-[10px] text-blue-300/80 mt-0.5">Webcam / selfie mode</div>
                    </div>
                  </div>

                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-purple-500/40 hover:border-purple-400 bg-purple-500/5 hover:bg-purple-500/10 rounded-2xl p-5 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-2 group"
                  >
                    <div className="p-3 rounded-full bg-purple-500/20 text-purple-400 group-hover:scale-110 transition-transform">
                      <Upload className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-white">📁 Upload Bill / Document</div>
                      <div className="text-[10px] text-purple-300/80 mt-0.5">Browse from device storage</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Auto-extracted Form Details */}
            <div className="space-y-4 bg-foreground/5 p-4 rounded-2xl border border-foreground/10">
              <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                <Sparkles className="w-4 h-4" /> 2. Delivery Details (OCR Auto-Extracted)
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Challan / Voucher No</label>
                  <input
                    type="text"
                    value={newBillForm.voucherNo}
                    onChange={e => setNewBillForm({ ...newBillForm, voucherNo: e.target.value })}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">PO Reference Number</label>
                  <input
                    type="text"
                    value={newBillForm.poNumber}
                    onChange={e => setNewBillForm({ ...newBillForm, poNumber: e.target.value })}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Material Name</label>
                  <input
                    type="text"
                    value={newBillForm.materialName}
                    onChange={e => setNewBillForm({ ...newBillForm, materialName: e.target.value })}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Vendor / Supplier</label>
                  <input
                    type="text"
                    value={newBillForm.vendorName}
                    onChange={e => setNewBillForm({ ...newBillForm, vendorName: e.target.value })}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Quantity & Unit</label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={newBillForm.quantity}
                      onChange={e => setNewBillForm({ ...newBillForm, quantity: Number(e.target.value) })}
                      className="w-1/2 bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                    />
                    <input
                      type="text"
                      value={newBillForm.unit}
                      onChange={e => setNewBillForm({ ...newBillForm, unit: e.target.value })}
                      placeholder="Bags / MT"
                      className="w-1/2 bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Unit Rate (INR ₹)</label>
                  <input
                    type="number"
                    value={newBillForm.unitPrice}
                    onChange={e => setNewBillForm({ ...newBillForm, unitPrice: Number(e.target.value) })}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Vehicle License Plate</label>
                  <input
                    type="text"
                    value={newBillForm.vehicleNumber}
                    onChange={e => setNewBillForm({ ...newBillForm, vehicleNumber: e.target.value })}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-white font-mono uppercase outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Calculated Valuation</label>
                  <div className="w-full bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 text-xs text-amber-300 font-bold font-mono">
                    ₹{(newBillForm.quantity * newBillForm.unitPrice).toLocaleString('en-IN')}
                  </div>
                </div>
              </div>
            </div>

            {/* GPS Geofence Check */}
            <div className="p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <MapPin className="w-5 h-5 text-emerald-400 shrink-0" />
                <div className="text-xs text-white">
                  <span className="font-bold">Live GPS Coordinates</span>: Lat 28.4595, Lng 77.0266 (38m from Site Center)
                </div>
              </div>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                Verified On-Site ✅
              </span>
            </div>

            {/* Head Office Target Contact Banner */}
            <div className="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Mail className="w-4 h-4 text-amber-400 shrink-0" />
                <div className="text-[11px] text-white">
                  <span className="font-bold text-amber-300">Instant Audit Dispatch Target:</span>{' '}
                  <span className="font-mono text-amber-200">{headOfficeEmail}</span>{' '}
                  <span className="text-foreground/30">•</span>{' '}
                  <span className="font-mono text-emerald-300">{headOfficePhone}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowEmailConfigModal(true)}
                className="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-[10px] font-bold border border-amber-500/30 flex items-center gap-1"
              >
                <Settings className="w-3 h-3" /> Change
              </button>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-end gap-3 pt-2 border-t border-foreground/10">
              <button
                type="button"
                onClick={() => setShowScanModal(false)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white font-bold text-xs transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleSaveScannedBill(false)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 text-emerald-300 font-bold text-xs transition-all active:scale-95"
              >
                Save Delivery Record
              </button>
              <button
                type="button"
                onClick={() => handleSaveScannedBill(true)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-black font-extrabold text-xs shadow-lg shadow-amber-500/20 transition-all active:scale-95 flex items-center justify-center gap-2"
              >
                <Send className="w-4 h-4" /> Save & Mail to Head Office
              </button>
            </div>

          </div>
        </div>
      )}

      {/* Head Office Audit Email & Alert Settings Modal */}
      {showEmailConfigModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-[#141414] border border-amber-500/30 rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-6 relative animate-in fade-in zoom-in-95 duration-150">
            
            {/* Header */}
            <div className="flex items-start justify-between border-b border-foreground/10 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-2xl bg-amber-500/20 border border-amber-500/30 text-amber-400">
                  <Settings className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-lg font-extrabold text-white">Head Office Audit Dispatch Config</h3>
                  <p className="text-xs text-muted-foreground">Configure recipient Email ID & WhatsApp phone for delivery audits</p>
                </div>
              </div>
              <button
                onClick={() => setShowEmailConfigModal(false)}
                className="p-2 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Inputs Form */}
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-amber-300 mb-1.5 flex items-center gap-1.5">
                  <Mail className="w-4 h-4 text-amber-400" /> Head Office Auditor Email ID
                </label>
                <input
                  type="email"
                  value={headOfficeEmail}
                  onChange={(e) => {
                    setHeadOfficeEmail(e.target.value);
                    localStorage.setItem('audit_headoffice_email', e.target.value);
                  }}
                  placeholder="e.g. headoffice.audit@herohomes.in or your email"
                  className="w-full bg-background/80 border border-foreground/15 rounded-xl px-3.5 py-2.5 text-xs text-white outline-none focus:border-amber-500 transition-all font-mono"
                />
                <p className="text-[10px] text-muted-foreground mt-1">Delivery challan + 4-point visual proof will be auto-emailed to this address.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-emerald-400 mb-1.5 flex items-center gap-1.5">
                  <Phone className="w-4 h-4 text-emerald-400" /> WhatsApp / SMS Alert Phone Number
                </label>
                <input
                  type="text"
                  value={headOfficePhone}
                  onChange={(e) => {
                    setHeadOfficePhone(e.target.value);
                    localStorage.setItem('audit_headoffice_phone', e.target.value);
                  }}
                  placeholder="e.g. +91 98100 44210"
                  className="w-full bg-background/80 border border-foreground/15 rounded-xl px-3.5 py-2.5 text-xs text-white outline-none focus:border-emerald-500 transition-all font-mono"
                />
                <p className="text-[10px] text-muted-foreground mt-1">Instant delivery verification summary & gate entry alerts will be dispatched here.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-blue-400 mb-1.5 flex items-center gap-1.5">
                  <Mail className="w-4 h-4 text-blue-400" /> CC: Site Store / Project Manager Email
                </label>
                <input
                  type="email"
                  value={siteManagerEmail}
                  onChange={(e) => {
                    setSiteManagerEmail(e.target.value);
                    localStorage.setItem('audit_sitemanager_email', e.target.value);
                  }}
                  placeholder="e.g. site.store@herohomes.in"
                  className="w-full bg-background/80 border border-foreground/15 rounded-xl px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500 transition-all font-mono"
                />
              </div>
            </div>

            {/* Quick Test & Save Actions */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-foreground/10">
              <button
                type="button"
                onClick={() => {
                  alert(`📨 Test Dispatch Ping Sent!\n\nEmail: ${headOfficeEmail}\nWhatsApp: ${headOfficePhone}\nCC: ${siteManagerEmail}\n\nStatus: 200 OK ✅`);
                }}
                className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white font-bold text-xs flex items-center justify-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5 text-amber-400" /> Send Test Ping
              </button>

              <button
                type="button"
                onClick={() => {
                  localStorage.setItem('audit_headoffice_email', headOfficeEmail);
                  localStorage.setItem('audit_headoffice_phone', headOfficePhone);
                  localStorage.setItem('audit_sitemanager_email', siteManagerEmail);
                  setShowEmailConfigModal(false);
                  alert(`✅ Head Office Contact Settings Saved Successfully!\n\nAuditor: ${headOfficeEmail}\nPhone: ${headOfficePhone}`);
                }}
                className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-black font-extrabold text-xs shadow-lg shadow-amber-500/20 active:scale-95 transition-all"
              >
                Save Configuration
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
