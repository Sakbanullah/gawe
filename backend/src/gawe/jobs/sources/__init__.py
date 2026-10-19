"""Source adapters. Only sources with official access documentation live here."""

from . import ashby, greenhouse, lever

ADAPTERS = {
    greenhouse.ATS: greenhouse,
    lever.ATS: lever,
    ashby.ATS: ashby,
}

__all__ = ["ADAPTERS", "ashby", "greenhouse", "lever"]
