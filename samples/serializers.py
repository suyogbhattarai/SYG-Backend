from rest_framework import serializers
from .models import SampleBasket


class SampleBasketSerializer(serializers.ModelSerializer):
    """Sample file in project basket"""
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    sample_uid = serializers.CharField(source='uid', read_only=True)  # <-- added

    class Meta:
        model = SampleBasket
        fields = [
            'sample_uid',  # <-- added
            'id',  # optional, keep for internal use
            'project', 'project_name', 'name', 'description',
            'file', 'file_url', 'file_size', 'file_size_mb', 'file_type',
            'tags', 'uploaded_at',
            'uploaded_by', 'uploaded_by_username'
        ]
        read_only_fields = ['id', 'sample_uid', 'uploaded_at', 'uploaded_by', 'file_size', 'file_type']
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class SampleBasketCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating sample"""
    class Meta:
        model = SampleBasket
        fields = ['name', 'description', 'file', 'tags']
    
    def validate_file(self, value):
        """Validate file upload"""
        max_size = 100 * 1024 * 1024  # 100MB
        if value.size > max_size:
            raise serializers.ValidationError("File size exceeds maximum allowed size of 100MB")
        return value


class SampleBasketUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating sample metadata"""
    class Meta:
        model = SampleBasket
        fields = ['name', 'description', 'tags', 'file']


class SampleBasketListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for sample lists"""
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    sample_uid = serializers.CharField(source='uid', read_only=True)  # <-- added

    class Meta:
        model = SampleBasket
        fields = [
            'sample_uid',  # <-- added
            'id',  # optional
            'name', 'file_type', 'file_size_mb',
            'uploaded_at', 'uploaded_by_username', 'tags'
        ]
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
