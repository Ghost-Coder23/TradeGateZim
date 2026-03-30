from django import forms

from .models import FeeSettings


class FeeSettingsForm(forms.ModelForm):
    class Meta:
        model = FeeSettings
        fields = ['deposit_fee_percent', 'withdrawal_fee_percent']
        widgets = {
            'deposit_fee_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'withdrawal_fee_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
        labels = {
            'deposit_fee_percent': 'Deposit Fee (%)',
            'withdrawal_fee_percent': 'Withdrawal Fee (%)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing_class} form-control".strip()
