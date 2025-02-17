from django.shortcuts import render, redirect
from django.views import View
from main.models import Donation, DonationCategories, \
    TokenTemporaryStorage
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str, DjangoUnicodeDecodeError
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.sites.shortcuts import get_current_site
from .utils import token_generator
from django.core.exceptions import ObjectDoesNotExist


class LoginView(View):
    def get(self, request):
        return render(request, 'login.html')

    def post(self, request):
        try:
            email = request.POST.get('email')
            password = request.POST.get('password')
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                return redirect('/')
            elif not User.objects.get(email=email).check_password(password):
                messages.error(request, 'Incorrect password')
                return render(request, 'login.html')
        except ObjectDoesNotExist:
            messages.error(request, 'Given e-mail does not exist in the database')
            return render(request, 'login.html')


class RegisterView(View):
    def get(self, request):
        return render(request, 'register.html')

    def post(self, request):
        name = request.POST.get('name')
        surname = request.POST.get('surname')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        if len(password) < 8 or len(password2) < 8:
            messages.error(request, 'Password too short (Min. 8 characters)')
            return render(request, 'register.html')
        elif any(not c.isalnum() for c in password2) is False \
                or any(c.isupper() for c in password2) is False \
                or any(c.islower() for c in password2) is False \
                or any(c.isdigit() for c in password2) is False:
            messages.error(request, 'The password does not have all special characters'
                                    '(There should be letters, lowercase letters, numbers and special characters)')
            return render(request, 'register.html')
        elif User.objects.filter(username=email):
            messages.error(request, 'A user with the given e-mail already exists')
            return render(request, 'register.html')
        elif password != password2:
            messages.error(request, 'Passwords mismatch')
            return render(request, 'register.html')
        user = User.objects.create_user(username=email, first_name=name, last_name=surname, email=email)
        user.set_password(password2)
        user.is_active = False
        user.save()

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = token_generator.make_token(user)
        TokenTemporaryStorage.objects.create(user_id=user.id, token=token)
        domain = get_current_site(request).domain
        link = reverse('activate-page', kwargs={'uidb64': uidb64, 'token': token})
        email_subject = 'Activate your account'
        activation_url = f'http://{domain}{link}'
        email_body = f'Hello {user}, your activation link:  {activation_url}'
        send_mail(
            email_subject,
            email_body,
            'noreply@noreply.com',
            [email],
            fail_silently=False,
        )
        messages.success(request, 'Check your e-mail account for further information')
        return render(request, 'register.html')


class VerificationView(View):
    def get(self, request, uidb64, token):
        try:
            id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(id=id)
            stored_token = TokenTemporaryStorage.objects.get(user=user).token
            if token == stored_token:
                TokenTemporaryStorage.objects.get(user=user).delete()
                if not token_generator.check_token(user, token):
                    messages.error(request, 'Account is already activated')
                    return redirect('login-page')
                if user.is_active:
                    return redirect('login-page')

                user.is_active = True
                user.save()

                messages.success(request, 'Account successfully activated')
                return redirect('login-page')
            else:
                messages.error(request, 'Incorrect link or account is already activated')
                return redirect('login-page')
        except ObjectDoesNotExist:
            messages.error(request, 'Incorrect link or account is already activated')
            return redirect('login-page')


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('/')


class UserPanelView(View):
    def get(self, request, user_id):
        donations = Donation.objects.filter(user_id=user_id).order_by('date_added') \
            .order_by('date_taken').order_by('time_taken').order_by('is_taken')
        donation_categories = DonationCategories.objects.all()
        return render(request, 'user_panel.html', {'donations': donations,
                                                         'donation_categories': donation_categories})

    def post(self, request, user_id):
        name = request.POST.get('name')
        surname = request.POST.get('surname')
        message = request.POST.get('message')
        email_subject = f'Contact form(Sent by user {name} {surname}'
        email_body = message
        administrators = User.objects.filter(is_superuser=True)

        if not name or not surname or not message:
            messages.error(request, 'Please fill all fields correctly')
            return redirect('/')

        for administrator in administrators:
            email = administrator.email
            send_mail(
                email_subject,
                email_body,
                'noreply@noreply.com',
                [email],
                fail_silently=False,
            )
        messages.success(request, 'Successfully sent')
        return redirect(f'/panel/{request.user.id}/')


class UserEditView(View):
    def get(self, request, user_id):
        if request.user.id != user_id:
            return redirect(f'/edit/{request.user.id}/')
        return render(request, 'user-edit.html')

    def post(self, request, user_id):
        user = User.objects.get(id=user_id)

        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        if not request.POST.get('password') or not request.POST.get('password2'):
            messages.error(request, 'Please fill all fields correctly')
            return render(request, 'user-edit.html')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        if password != password2:
            messages.error(request, 'Passwords mismatch')
            return render(request, 'user-edit.html')
        user = authenticate(request, username=request.user.email, password=password2)
        if user is None:
            messages.error(request, 'Incorrect password')
            return render(request, 'user-edit.html')
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.save()
        messages.success(request, 'Data has been changed')
        return redirect(f'/edit/{request.user.id}/')


class PasswordChangeView(View):
    def get(self, request, user_id):
        if request.user.id != user_id:
            return redirect(f'/edit/{request.user.id}/')
        return render(request, 'change-password.html')

    def post(self, request, user_id):
        if not request.POST.get('old_password') or not request.POST.get('new_password1') or not request.POST.get(
                'new_password2'):
            messages.error(request, 'Please fill all fields correctly')
            return render(request, 'change-password.html')

        old_password = request.POST.get('old_password')
        user = authenticate(request, username=request.user.email, password=old_password)
        if user is None:
            messages.error(request, 'Old password incorrect')
            return render(request, 'change-password.html')

        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        if new_password1 != new_password2:
            messages.error(request, 'Passwords mismatch')
            return render(request, 'change-password.html')

        user.set_password(new_password1)
        user.save()
        new_user = authenticate(request, username=request.user.email, password=new_password1)
        if user is None:
            messages.error(request, 'Something went wrong')
            return render(request, 'change-password.html')
        login(request, new_user)
        messages.success(request, 'Data successfully changed')
        return redirect(f'/edit/{request.user.id}/')


class PasswordResetView(View):
    def get(self, request):
        return render(request, 'password-reset.html')

    def post(self, request):
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            TokenTemporaryStorage.objects.create(user_id=user.id, token=token)
            domain = get_current_site(request).domain
            link = reverse('password-reset-verification', kwargs={'uidb64': uidb64, 'token': token})
            email_subject = 'Password reset'
            activation_url = f'http://{domain}{link}'
            email_body = f'Hello {user}, twój password reset link:  {activation_url}'
            send_mail(
                email_subject,
                email_body,
                'noreply@noreply.com',
                [email],
                fail_silently=False,
            )
            messages.success(request, 'Check your e-mail inbox')
            return render(request, 'password-reset.html')
        except ObjectDoesNotExist:
            messages.error(request, 'Incorrect e-mail')
            return render(request, 'password-reset.html')


class PasswordResetVerificationView(View):
    def get(self, request, uidb64, token):
        try:
            id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(id=id)
            stored_token = TokenTemporaryStorage.objects.get(user=user).token
            if token == stored_token:
                if not token_generator.check_token(user, token):
                    messages.error(request, 'Password has already been changed')
                    return redirect('login-page')
                return render(request, 'new-password-form.html')
            else:
                messages.error(request, 'Incorrect link or password is already changed')
                return redirect('login-page')
        except ObjectDoesNotExist:
            messages.error(request, 'Incorrect link or password is already changed')
            return redirect('login-page')

    def post(self, request, uidb64, token):
        id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(id=id)
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            messages.error(request, 'Passwords mismatch')
            return render(request, 'new-password-form.html')

        user.set_password(password1)
        user.save()
        TokenTemporaryStorage.objects.get(user=user).delete()

        messages.success(request, 'Password changed successfully')
        return redirect('login-page')
