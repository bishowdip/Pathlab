from .models import SiteSettings


def site_settings(request):
    try:
        return {"site": SiteSettings.load()}
    except Exception:
        return {"site": None}
