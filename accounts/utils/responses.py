from rest_framework.response import Response
from rest_framework import status

def success_response(message, data=None, code=status.HTTP_200_OK):
    """Standard success response format"""
    return Response({
        "success": True,
        "message": message,
        "data": data or {}
    }, status=code)


def error_response(message, errors=None, code=status.HTTP_400_BAD_REQUEST):
    """Standard error response format"""
    return Response({
        "success": False,
        "message": message,
        "errors": errors or {}
    }, status=code)
