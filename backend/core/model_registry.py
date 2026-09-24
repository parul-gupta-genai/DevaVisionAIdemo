class ModelRegistryItem:
    def __init__(self, name="ANPR Model", status="VERIFIED"):
        self.name = name
        self.status = status

class ModelRegistry:
    def list_models(self):
        return [
            ModelRegistryItem("ANPR License Plate", "VERIFIED"),
            ModelRegistryItem("YOLO Vehicle Detector", "VERIFIED"),
        ]

model_registry = ModelRegistry()
