from django import forms

from .models import Settings


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super(SettingsForm, self).__init__(*args, **kwargs)
