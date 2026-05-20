def staff_context(request):
    """Foydalanuvchi staff bo'lsa, postal_office va boshqa info beradi.

    Templatega:
      staff_postal_office, staff_full_name — xodim ma'lumotlari
      can_enter_surveys — so'rovnoma kirita oladimi
      has_admin_view_access — kuzatuv/hisobot panellariga kirish huquqi bormi
    """
    ctx = {
        'staff_postal_office': None,
        'staff_full_name': '',
        # Default: ruxsat bor (superuser yoki StaffProfile yo'q bo'lsa ham)
        'can_enter_surveys': True,
        # Default: yo'q (faqat superuser yoki kuzatuvchi staff)
        'has_admin_view_access': False,
    }
    if not request.user.is_authenticated:
        return ctx
    user = request.user
    # Superuser doim hammasiga ega
    if user.is_superuser:
        ctx['has_admin_view_access'] = True
    try:
        profile = user.staff_profile
        ctx['staff_postal_office'] = profile.postal_office
        if not user.is_superuser:
            ctx['can_enter_surveys'] = bool(profile.can_enter_surveys)
            # Cheklangan staff (can_enter_surveys=False) — kuzatuvchi
            if not profile.can_enter_surveys:
                ctx['has_admin_view_access'] = True
    except Exception:
        pass
    ctx['staff_full_name'] = user.get_full_name() or user.username
    return ctx
