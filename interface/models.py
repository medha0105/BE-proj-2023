from django.db import models

# Create your models here.
class Document(models.Model):
    pdf = models.FileField(upload_to = None)
    

class Sections(models.Model):
    text_file = models.FileField(upload_to = None)
    key = models.ForeignKey(Document, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return str(self.text_file)
