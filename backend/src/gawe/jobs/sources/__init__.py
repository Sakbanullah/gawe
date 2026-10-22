"""Source adapters. Only sources with official access documentation live here."""

from . import ashby, greenhouse, himalayas, lever

ADAPTERS = {
    greenhouse.ATS: greenhouse,
    lever.ATS: lever,
    ashby.ATS: ashby,
    himalayas.ATS: himalayas,
}

__all__ = ["ADAPTERS", "ashby", "greenhouse", "himalayas", "lever"]
