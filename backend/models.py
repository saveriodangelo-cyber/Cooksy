from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Recipe:
    id: Optional[str] = None
    title: str = ""
    category: str = ""
    ingredients: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
