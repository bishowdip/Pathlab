from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import Profile

User = get_user_model()


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    # `role` here is limited to the two safe self-service choices — instructor
    # accounts are granted by staff, not self-selected at signup.
    role = forms.ChoiceField(
        choices=[("student", "Student"), ("kid", "Kid")],
        initial="student", required=True,
        help_text="Pick 'Kid' if this account is for a school-age learner."
    )
    country = forms.CharField(max_length=50, required=False, initial="Nepal")

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile = user.profile  # signal-created
            profile.role = self.cleaned_data["role"]
            profile.country = self.cleaned_data.get("country") or "Nepal"
            profile.save()
        return user


class ProfileForm(forms.ModelForm):
    """Self-service profile edit. `role` is intentionally NOT exposed — instructor
    elevation is a staff-only action done in the Django admin."""
    class Meta:
        model = Profile
        fields = ("phone", "country", "avatar")
