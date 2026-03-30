
from django.conf import settings

def global_settings(request):
    return {
        'simulation_mode': getattr(settings, 'SIMULATION_MODE', True),
        'platform_name': getattr(settings, 'PLATFORM_NAME', 'TradeGate ZW'),
    }
