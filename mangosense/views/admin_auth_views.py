import json
from django.http import JsonResponse
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework_simplejwt.tokens import RefreshToken

@csrf_exempt
@require_http_methods(["POST"])
def admin_login_api(request):
    """Admin login endpoint for Angular frontend"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return JsonResponse({
                'success': False,
                'error': 'Username and password are required'
            }, status=400)
        
        # Authenticate user
        user = authenticate(username=username, password=password)
        
        if user is not None and user.is_active:
            # Check if user is superuser (admin)
            if user.is_superuser:
                # Generate JWT tokens
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                
                return JsonResponse({
                    'success': True,
                    'access': str(access_token),
                    'refresh': str(refresh),
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'is_superuser': user.is_superuser,
                        'email': user.email
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied. Admin privileges required.'
                }, status=403)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid credentials'
            }, status=401)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def admin_refresh_token(request):
    """Refresh JWT token for admin"""
    try:
        data = json.loads(request.body)
        refresh_token = data.get('refresh')
        
        if not refresh_token:
            return JsonResponse({
                'success': False,
                'error': 'Refresh token is required'
            }, status=400)
        
        try:
            refresh = RefreshToken(refresh_token)
            access_token = refresh.access_token
            
            return JsonResponse({
                'success': True,
                'access': str(access_token)
            })
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'Invalid refresh token'
            }, status=401)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)