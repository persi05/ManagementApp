from django.contrib import admin

from .models import DocumentAccess, DocumentItem, DocumentPin, DocumentVisibilityBlock


class DocumentAccessInline(admin.TabularInline):
    model = DocumentAccess
    extra = 0


class DocumentVisibilityBlockInline(admin.TabularInline):
    model = DocumentVisibilityBlock
    extra = 0


class DocumentPinInline(admin.TabularInline):
    model = DocumentPin
    extra = 0


@admin.register(DocumentItem)
class DocumentItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'owner', 'parent', 'is_pinned', 'is_archived', 'updated_at')
    list_filter = ('kind', 'is_archived', 'is_pinned')
    search_fields = ('name', 'content')
    inlines = [DocumentAccessInline, DocumentVisibilityBlockInline, DocumentPinInline]
