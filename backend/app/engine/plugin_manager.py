import os
import importlib
import inspect
from typing import List, Dict, Type
from loguru import logger

from app.engine.base import BaseDetectionPlugin

class PluginManager:
    """
    Dynamically discovers and loads plugins from the app/plugins directory.
    """
    def __init__(self, app_config, plugins_dir: str = "app/plugins"):
        self.app_config = app_config
        self.plugins_dir = plugins_dir
        
    def discover_plugin_classes(self) -> List[Type[BaseDetectionPlugin]]:
        """
        Scans the plugins directory and returns a list of plugin classes.
        Does NOT instantiate them.
        """
        plugin_classes = []
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        plugins_abs_path = os.path.join(base_path, "plugins")
        
        if not os.path.exists(plugins_abs_path):
            logger.error(f"Plugin directory not found: {plugins_abs_path}")
            return plugin_classes

        # Dynamic scanning of the plugins directory

        for item in os.listdir(plugins_abs_path):
            item_path = os.path.join(plugins_abs_path, item)
            if os.path.isdir(item_path) and os.path.isfile(os.path.join(item_path, "plugin.py")):
                plugin_module_name = f"app.plugins.{item}.plugin"
                try:
                    module = importlib.import_module(plugin_module_name)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseDetectionPlugin) and obj is not BaseDetectionPlugin:
                            plugin_classes.append(obj)
                except Exception as e:
                    logger.error(f"Failed to load plugin class from {plugin_module_name}: {e}")
                    
        return plugin_classes
        
    def discover_plugins(self) -> List[BaseDetectionPlugin]:
        """Legacy wrapper that instantiates all discovered classes."""
        loaded_plugins = []
        for plugin_class in self.discover_plugin_classes():
            try:
                plugin_instance = plugin_class(app_config=self.app_config)
                loaded_plugins.append(plugin_instance)
                logger.info(f"Dynamically loaded plugin: {plugin_instance.plugin_name}")
            except Exception as e:
                logger.error(f"Failed to load plugin: {e}")
        return loaded_plugins
