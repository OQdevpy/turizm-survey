def staff_context(request):
    """Foydalanuvchi staff bo'lsa, postal_office va boshqa info beradi."""
    ctx = {
        'staff_postal_office': None,
        'staff_full_name': '',
    }
    if request.user.is_authenticated:
        try:
            profile = request.user.staff_profile
            ctx['staff_postal_office'] = profile.postal_office
        except Exception:
            pass
        ctx['staff_full_name'] = request.user.get_full_name() or request.user.username
    return ctx
