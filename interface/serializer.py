from .models import Document
from rest_framework.serializers import ModelSerializer

class DocumentSerializer(ModelSerializer):
    class Meta:
        model = Document
        fields = ['id','pdf']