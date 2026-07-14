from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from features.accounts.forms import AccountForm, RegisterForm
from features.accounts.models import UserProfile, ensure_profile


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.is_active = False
            user.save()
            profile = ensure_profile(user)
            profile.role = UserProfile.Role.CLIENT
            profile.save()
            send_registration_confirmation(request, user)
            messages.success(request, 'Konto zostało utworzone. Sprawdź e-mail i potwierdź rejestrację.')
            return redirect('accounts:activation_sent')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


def activation_sent(request):
    return render(request, 'registration/activation_sent.html')


def activate_account(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=['is_active'])
        login(request, user)
        messages.success(request, 'Konto zostało potwierdzone.')
        return redirect('dashboard')

    return render(request, 'registration/activation_invalid.html', status=400)


@login_required
def account_settings(request):
    if request.method == 'POST' and request.POST.get('form') == 'profile':
        account_form = AccountForm(request.POST, instance=request.user)
        password_form = PasswordChangeForm(request.user)
        if account_form.is_valid():
            account_form.save()
            messages.success(request, 'Dane konta zostały zapisane.')
            return redirect('accounts:settings')
    elif request.method == 'POST' and request.POST.get('form') == 'password':
        account_form = AccountForm(instance=request.user)
        password_form = PasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, password_form.user)
            messages.success(request, 'Hasło zostało zmienione.')
            return redirect('accounts:settings')
    else:
        account_form = AccountForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(request, 'registration/account_settings.html', {
        'account_form': account_form,
        'password_form': password_form,
    })


def send_registration_confirmation(request, user):
    if not user.email:
        return
    activation_url = request.build_absolute_uri(reverse('accounts:activate', kwargs={
        'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': default_token_generator.make_token(user),
    }))
    context = {
        'user': user,
        'login_url': request.build_absolute_uri('/accounts/login/'),
        'activation_url': activation_url,
    }
    send_mail(
        'Potwierdź rejestrację - Dcode Management',
        render_to_string('registration/emails/registration_confirmation.txt', context),
        None,
        [user.email],
        html_message=render_to_string('registration/emails/registration_confirmation.html', context),
        fail_silently=True,
    )
