"""GET /admin/rules - the plain-English rule book for each feature.

Serves the reader's view: the rules as a business reader needs them, with no
source paths, document names or code output (see rules_catalog.reader_view).

The feature list is WIDGET_REGISTRY's, not the catalog's: a feature with no
catalog file is reported in `missing`, so a new feature cannot be added without
the Rules page saying it is undocumented.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.widgets import WIDGET_REGISTRY
from app.core.deps import require_admin_role
from app.database.mongodb import get_db
from app.services import rules_catalog
from app.services.rules_catalog import reference

router = APIRouter(prefix="/admin/rules", tags=["Rules (Admin Only)"])


@router.get("")
def list_feature_rules(current_user: dict = Depends(require_admin_role)):
    documented = set(rules_catalog.catalog_keys())
    return {
        "features": [rules_catalog.reader_summary(k) for k in WIDGET_REGISTRY if k in documented],
        "missing": [k for k in WIDGET_REGISTRY if k not in documented],
    }


@router.get("/reference")
def list_reference_sets(current_user: dict = Depends(require_admin_role)):
    """The fixed rule sets the features apply (the rulebook, lifecycle, ...)."""
    return {"sets": reference.reference_index(get_db())}


@router.get("/reference/{key}")
def get_reference_set(key: str, current_user: dict = Depends(require_admin_role)):
    if key not in reference.REFERENCE_SETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No rule set named '%s'." % key)
    return reference.reference_set(get_db(), key)


# Declared after /reference so that path is not read as a feature key.
@router.get("/{feature_key}")
def get_feature_rules(feature_key: str, current_user: dict = Depends(require_admin_role)):
    if feature_key not in WIDGET_REGISTRY or feature_key not in rules_catalog.catalog_keys():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No rules documented for feature '%s'." % feature_key)
    return rules_catalog.reader_view(feature_key)
