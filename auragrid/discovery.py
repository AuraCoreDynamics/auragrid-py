import json
import os
import platform
from dataclasses import dataclass
from typing import List

@dataclass
class DiscoveredNode:
    NodeId: str
    InstallDir: str
    DataDir: str
    Version: str
    ManagementPort: int

class LocalNodeDiscovery:
    """Utility for discovering locally installed AuraGrid nodes across the host OS."""

    @staticmethod
    def get_registry_path() -> str:
        """Returns the OS-specific path to the global nodes registry file."""
        if platform.system() == "Windows":
            base_path = os.path.join(os.environ.get("ALLUSERSPROFILE", "C:\\ProgramData"), "AuraGrid")
        else:
            base_path = "/etc/auragrid"
        
        return os.path.join(base_path, "installed-nodes.json")

    @staticmethod
    def discover_nodes() -> List[DiscoveredNode]:
        """Reads the global registry and returns a list of installed AuraGrid nodes."""
        path = LocalNodeDiscovery.get_registry_path()
        if not os.path.exists(path):
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            nodes_data = data.get("Nodes", [])
            results = []
            for item in nodes_data:
                results.append(DiscoveredNode(
                    NodeId=item.get("NodeId", ""),
                    InstallDir=item.get("InstallDir", ""),
                    DataDir=item.get("DataDir", ""),
                    Version=item.get("Version", ""),
                    ManagementPort=item.get("ManagementPort", 0)
                ))
            return results
        except Exception:
            # Silently fail on permission errors or malformed JSON, as expected in discovery logic
            return []
