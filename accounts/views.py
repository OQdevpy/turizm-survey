from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .forms import StaffLoginForm


@never_cache
@csrf_protect
def staff_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    if request.method == 'POST':
        form = StaffLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not (user.is_staff or user.is_superuser):
                form.add_error(None, "Sizda kirish huquqi yo'q. Faqat xodimlar uchun.")
            else:
                auth_login(request, user)
                next_url = request.GET.get('next') or 'dashboard:index'
                return redirect(next_url)
    else:
        form = StaffLoginForm(request)

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def staff_logout(request):
    auth_logout(request)
    return redirect('home')
