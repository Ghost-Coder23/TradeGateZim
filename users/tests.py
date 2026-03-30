from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model


class AuthRouteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='route_user',
            password='pass12345',
        )

    def test_register_login_and_logout(self):
        response = self.client.post(reverse('register'), {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'phone': '+263771234567',
            'country': 'ZW',
            'username': 'newuser',
            'password1': 'pass12345',
            'password2': 'pass12345',
        })
        self.assertRedirects(response, reverse('dashboard'))

        logout_get = self.client.get(reverse('logout'))
        self.assertRedirects(logout_get, reverse('login'))

        logout_post = self.client.post(reverse('logout'))
        self.assertRedirects(logout_post, reverse('login'))

        login_response = self.client.post(reverse('login'), {
            'username': 'route_user',
            'password': 'pass12345',
        })
        self.assertRedirects(login_response, reverse('dashboard'))

    @override_settings(
        RATE_LIMITS={
            'login_ip': {'limit': 1, 'window': 60},
            'login_username': {'limit': 1, 'window': 60},
        }
    )
    def test_login_is_rate_limited(self):
        first_response = self.client.post(reverse('login'), {
            'username': 'route_user',
            'password': 'wrong-pass',
        })
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(reverse('login'), {
            'username': 'route_user',
            'password': 'wrong-pass',
        })
        self.assertEqual(second_response.status_code, 429)

    @override_settings(
        RATE_LIMITS={
            'register_ip': {'limit': 1, 'window': 60},
        }
    )
    def test_register_is_rate_limited(self):
        invalid_payload = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'phone': '+263771234567',
            'country': 'ZW',
            'username': 'rateuser',
            'password1': 'pass12345',
            'password2': 'different-pass',
        }

        first_response = self.client.post(reverse('register'), invalid_payload)
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(reverse('register'), invalid_payload)
        self.assertEqual(second_response.status_code, 429)
