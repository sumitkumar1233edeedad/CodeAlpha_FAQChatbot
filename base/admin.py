from django.contrib import admin

from .models import Document, DocumentChunk


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    fields = ("order", "text")
    readonly_fields = ("order", "text")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "file", "status", "uploaded_at")
    readonly_fields = ("status", "error_message", "uploaded_at")
    inlines = [DocumentChunkInline]
