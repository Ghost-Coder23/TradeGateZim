from decimal import Decimal

from django import forms

from .models import Transaction


class PaymentDetailsValidationMixin(forms.Form):
    payer_number = forms.CharField(
        max_length=20,
        required=False,
        label="Mobile Number",
        widget=forms.TextInput(attrs={'placeholder': '+263771234567', 'class': 'form-control'}),
    )
    bank_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CBZ, Stanbic, etc'}),
    )
    bank_account = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your bank account number'}),
    )

    mobile_payment_methods = {'ecocash', 'innbucks', 'onemoney'}

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount < Decimal('10.00'):
            raise forms.ValidationError('Amount must be at least $10.00.')
        if amount > Decimal('5000.00'):
            raise forms.ValidationError('Amount must not exceed $5000.00.')
        return amount

    def clean_payer_number(self):
        return self.cleaned_data.get('payer_number', '').strip()

    def clean_bank_name(self):
        return self.cleaned_data.get('bank_name', '').strip()

    def clean_bank_account(self):
        return self.cleaned_data.get('bank_account', '').strip()

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        payer_number = cleaned_data.get('payer_number', '')
        bank_name = cleaned_data.get('bank_name', '')
        bank_account = cleaned_data.get('bank_account', '')

        if payment_method in self.mobile_payment_methods and not payer_number:
            self.add_error('payer_number', 'A mobile number is required for this payment method.')

        if payment_method == 'bank_transfer':
            if not bank_name:
                self.add_error('bank_name', 'Bank name is required for bank transfers.')
            if not bank_account:
                self.add_error('bank_account', 'Bank account is required for bank transfers.')

        return cleaned_data

    def get_payment_data(self):
        return {
            'payer_number': self.cleaned_data.get('payer_number', ''),
            'bank_name': self.cleaned_data.get('bank_name', ''),
            'bank_account': self.cleaned_data.get('bank_account', ''),
        }


class DepositForm(PaymentDetailsValidationMixin, forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['platform', 'amount', 'payment_method', 'destination_account']
        widgets = {
            'destination_account': forms.TextInput(attrs={'placeholder': 'Your Binance UID or broker account ID'}),
            'amount': forms.NumberInput(attrs={'min': '10', 'max': '5000', 'step': '0.01'}),
        }
        labels = {
            'destination_account': 'Wallet / Account ID',
            'platform': 'Trading Platform',
            'payment_method': 'Pay Using',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        self.fields['payer_number'].label = 'Your Mobile Number'
        self.fields['bank_name'].label = 'Your Bank Name'
        self.fields['bank_account'].label = 'Your Bank Account'


class WithdrawalForm(PaymentDetailsValidationMixin, forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['platform', 'amount', 'payment_method', 'destination_account']
        widgets = {
            'destination_account': forms.TextInput(attrs={
                'placeholder': 'Your broker account ID (we pull funds from here)',
                'class': 'form-control'
            }),
            'amount': forms.NumberInput(attrs={'min': '10', 'max': '5000', 'step': '0.01', 'class': 'form-control'}),
        }
        labels = {
            'destination_account': 'Broker / Exchange Account ID',
            'platform': 'Withdraw From',
            'payment_method': 'Receive Via',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['platform'].widget.attrs['class'] = 'form-control'
        self.fields['payment_method'].widget.attrs['class'] = 'form-control'
        self.fields['payer_number'].label = 'EcoCash / Mobile Number'
        self.fields['bank_name'].label = 'Bank Name'
        self.fields['bank_account'].label = 'Bank Account'
