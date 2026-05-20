def staff_context(request):
    """Foydalanuvchi staff bo'lsa, postal_office va boshqa info beradi."""
    ctx = {
        'staff_postal_office': None,
        'staff_full_name': '',
        # Default: ruxsat bor (superuser yoki StaffProfile yo'q bo'lsa ham)
        'can_enter_surveys': True,
    }
    if request.user.is_authenticated:
        try:
            profile = request.user.staff_profile
            ctx['staff_postal_office'] = profile.postal_office
            # Superuser doim kira oladi
            if not request.user.is_superuser:
                ctx['can_enter_surveys'] = bool(profile.can_enter_surveys)
        except Exception:
            pass
        ctx['staff_full_name'] = request.user.get_full_name() or request.user.username
    return ctx
