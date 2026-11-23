from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Max, Min
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from . import models as m
from .importer import SORT_STEP
from .ordering import next_sort, place_by_date_desc
from .services import SongIndex, create_event_for_live, register_titles, save_setlist, suggest_live_id, unknown_titles
from .setlist_text import SetlistSyntaxError, parse, to_text


class AppendOrderMixin:
    """インラインで新しく追加した行を、同じ親の既存の行の後ろに並べる。

    ORDER_FIELDS = {インラインのモデル: (並び順の欄, 親を指す欄, 刻み)}
    """
    ORDER_FIELDS = {
        m.SongCD: ("ord", "song", 1),
        m.LiveArtist: ("ord", "live", 1),
        m.EventArtist: ("ord", "event", 1),
        m.ChecklistEntry: ("sort", "group", SORT_STEP),
    }

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            spec = self.ORDER_FIELDS.get(type(obj))
            if spec and obj.pk is None and getattr(obj, spec[0]) == 0:
                field, parent, step = spec
                current = (type(obj).objects.filter(**{parent: getattr(obj, parent)})
                           .aggregate(v=Max(field))["v"])
                if current is not None:
                    setattr(obj, field, current + step)
            obj.save()
        formset.save_m2m()


# ---- アーティスト・CD・曲 ----

@admin.register(m.Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ["name", "css_class", "sort"]
    list_editable = ["sort"]
    search_fields = ["name"]


@admin.register(m.CD)
class CDAdmin(admin.ModelAdmin):
    list_display = ["title", "type", "artist", "release_date"]
    list_filter = ["type", "artist"]
    search_fields = ["title"]
    date_hierarchy = "release_date"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.sort = next_sort(m.CD)
        super().save_model(request, obj, form, change)


class SongCDInline(admin.TabularInline):
    model = m.SongCD
    autocomplete_fields = ["cd"]
    extra = 0


class SongAliasInline(admin.TabularInline):
    model = m.SongAlias
    extra = 0


@admin.register(m.Song)
class SongAdmin(AppendOrderMixin, admin.ModelAdmin):
    list_display = ["title", "artist", "in_catalog", "length", "performed"]
    ordering = ["sort", "id"]
    list_filter = ["in_catalog", "artist"]
    search_fields = ["title", "aliases__alias"]
    inlines = [SongCDInline, SongAliasInline]
    fieldsets = [
        (None, {"fields": ["title", "artist", "in_catalog"]}),
        ("クレジット", {"fields": ["lyrics", "music", "arranger", "length"]}),
        ("リンク", {"fields": ["utanet", "mv", "video", "dance", "other", "call"]}),
        (None, {"fields": ["info"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(performed_lives=Count("setlistitem__live", distinct=True))

    @admin.display(description="披露した公演数", ordering="performed_lives")
    def performed(self, obj):
        return obj.performed_lives

    def save_model(self, request, obj, form, change):
        if not change:
            obj.sort = next_sort(m.Song)
        super().save_model(request, obj, form, change)


@admin.register(m.SongAlias)
class SongAliasAdmin(admin.ModelAdmin):
    list_display = ["alias", "song"]
    search_fields = ["alias", "song__title"]
    autocomplete_fields = ["song"]


# ---- ツアー・公演・セットリスト ----

@admin.register(m.Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ["title", "compare_artist", "compare_sort", "compare_default", "live_count"]
    list_filter = ["compare_artist"]
    list_editable = ["compare_sort"]
    search_fields = ["title"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(lives=Count("live"))

    @admin.display(description="公演数", ordering="lives")
    def live_count(self, obj):
        return obj.lives


class LiveArtistInline(admin.TabularInline):
    model = m.LiveArtist
    extra = 0
    min_num = 1


class SetlistItemInline(admin.TabularInline):
    model = m.SetlistItem
    autocomplete_fields = ["song"]
    extra = 0
    fields = ["section", "pos", "sub_pos", "song"]


class ChecklistEntryForLiveInline(admin.TabularInline):
    model = m.ChecklistEntry
    autocomplete_fields = ["group"]
    extra = 0
    fields = ["group", "label", "sort"]
    verbose_name_plural = "未回収チェックでの表示（見出しと表示名）"


class LiveForm(forms.ModelForm):
    create_event = forms.BooleanField(
        label="対応するイベントも作る", required=False, initial=True,
        help_text="日付・公演名・会場・出演を引き継いでイベントを作ります。分類や開始時刻はあとでイベントの画面で追記してください。")

    class Meta:
        model = m.Live
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "id" in self.fields:
            self.fields["id"].required = False
            self.fields["id"].help_text = "空のままにすると、開催日から自動で決めます（例: 2025112401）"

    def clean(self):
        data = super().clean()
        if "id" in self.fields and not data.get("id") and data.get("date"):
            data["id"] = suggest_live_id(data["date"])
            self.instance.id = data["id"]
        live_id, date = data.get("id") or self.instance.id, data.get("date")
        if live_id and date and live_id[:8] != date.strftime("%Y%m%d"):
            raise ValidationError("公演IDの先頭8桁は開催日と同じにしてください。")
        return data


@admin.register(m.Live)
class LiveAdmin(AppendOrderMixin, admin.ModelAdmin):
    form = LiveForm
    list_display = ["id", "date", "title", "tour", "venue", "songs", "verify_status"]
    list_filter = ["artists", "verify_status"]
    search_fields = ["id", "title", "venue", "tour__title", "verify_source", "verify_note"]
    date_hierarchy = "date"
    autocomplete_fields = ["tour"]
    inlines = [LiveArtistInline, SetlistItemInline, ChecklistEntryForLiveInline]
    actions = ["create_events"]
    change_form_template = "admin/catalog/live/change_form.html"
    exclude = ["sort"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(song_count=Count("setlist_items"))

    @admin.display(description="曲数", ordering="song_count")
    def songs(self, obj):
        return obj.song_count

    def get_readonly_fields(self, request, obj=None):
        # 公演ID は主キーなので、作ったあとは変えない（変えると別の公演になる）
        return ["id"] if obj else []

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        # イベントを一緒に作れるのは追加するときだけ
        return [f for f in fields if f != "create_event"] if obj else fields

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # 出演者（インライン）を保存したあとで作り、イベントにも引き継ぐ
        if not change and form.cleaned_data.get("create_event"):
            event = create_event_for_live(form.instance)
            messages.info(request, f"イベント「{event.title}」を作りました。")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change or "date" in form.changed_data:
            place_by_date_desc(obj)

    def response_add(self, request, obj, post_url_continue=None):
        if not obj.setlist_items.exists() and "_addanother" not in request.POST:
            messages.info(request, "続けてセットリストを入力してください。")
            return redirect("admin:catalog_live_setlist_text", obj.pk)
        return super().response_add(request, obj, post_url_continue)

    @admin.action(description="選んだ公演からイベントを作る（日付・タイトル・会場・出演者を引き継ぐ）")
    def create_events(self, request, queryset):
        created = [create_event_for_live(live) for live in queryset]
        messages.success(request, f"イベントを {len(created)} 件作りました。分類や開始時刻はイベントの画面で追記してください。")

    def get_urls(self):
        return [path("<path:object_id>/setlist-text/", self.admin_site.admin_view(self.setlist_text_view),
                     name="catalog_live_setlist_text")] + super().get_urls()

    def setlist_text_view(self, request, object_id):
        live = get_object_or_404(m.Live, pk=object_id)
        if not self.has_change_permission(request, live):
            raise PermissionDenied
        context = {**self.admin_site.each_context(request), "title": f"セットリストの一括入力: {live}",
                   "live": live, "opts": self.model._meta, "original": live, "error": None, "unknown": []}
        if request.method != "POST":
            context["text"] = to_text(live)
            return TemplateResponse(request, "admin/catalog/live/setlist_text.html", context)

        text = context["text"] = request.POST.get("text", "")
        try:
            entries = parse(text)
        except SetlistSyntaxError as e:
            context["error"] = str(e)
            return TemplateResponse(request, "admin/catalog/live/setlist_text.html", context)

        if request.POST.get("step") == "resolve":
            decisions, errors = self._read_decisions(request)
            if errors:
                context["error"] = " ".join(errors)
            else:
                register_titles(decisions)

        index = SongIndex()
        unknown = unknown_titles(entries, index)
        if not unknown:
            count = save_setlist(live, entries)
            messages.success(request, f"セットリストを保存しました（{count} 曲）。")
            return redirect("admin:catalog_live_change", live.pk)
        context["unknown"] = [{"title": t, "candidates": c} for t, c in unknown.items()]
        context["song_titles"] = sorted(index.by_title)
        return TemplateResponse(request, "admin/catalog/live/setlist_text.html", context)

    @staticmethod
    def _read_decisions(request):
        """確認画面の選択を読む。choice_N: "alias:<曲ID>" / "existing"（target_N に曲名）/ "new" """
        decisions, errors, index = {}, [], SongIndex()
        n = 0
        while f"title_{n}" in request.POST:
            title, choice = request.POST[f"title_{n}"], request.POST.get(f"choice_{n}", "")
            if choice.startswith("alias:"):
                decisions[title] = ("alias", get_object_or_404(m.Song, pk=choice[6:]))
            elif choice == "existing":
                song, _ = index.resolve(request.POST.get(f"target_{n}", ""))
                if song is None:
                    errors.append(f"「{title}」の対応先の曲が見つかりません。曲名を正確に入力してください。")
                else:
                    decisions[title] = ("alias", song)
            elif choice == "new":
                decisions[title] = ("new", None)
            else:
                errors.append(f"「{title}」の扱いを選んでください。")
            n += 1
        return decisions, errors


# ---- イベント ----

class EventArtistInline(admin.TabularInline):
    model = m.EventArtist
    extra = 0
    min_num = 1


@admin.register(m.Event)
class EventAdmin(AppendOrderMixin, admin.ModelAdmin):
    list_display = ["date", "weekday", "start_time", "title", "class1", "class2", "venue", "setlist_link"]
    list_filter = ["class1", "class2", "artists"]
    search_fields = ["title", "title2", "venue", "sponsor", "info"]
    date_hierarchy = "date"
    autocomplete_fields = ["live"]
    inlines = [EventArtistInline]
    exclude = ["sort"]

    @admin.display(description="曜日")
    def weekday(self, obj):
        return obj.weekday

    @admin.display(description="セットリスト")
    def setlist_link(self, obj):
        if not obj.live_id:
            return ""
        return format_html('<a href="{}">{}</a>', reverse("admin:catalog_live_change", args=[obj.live_id]), obj.live_id)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change or "date" in form.changed_data:
            place_by_date_desc(obj)


# ---- 未回収楽曲チェック ----

class ChecklistEntryInline(admin.TabularInline):
    model = m.ChecklistEntry
    autocomplete_fields = ["live"]
    extra = 0
    fields = ["live", "label", "sort"]


@admin.register(m.ChecklistGroup)
class ChecklistGroupAdmin(AppendOrderMixin, admin.ModelAdmin):
    list_display = ["heading", "artist", "sort", "entry_count"]
    list_filter = ["artist"]
    list_editable = ["sort"]
    search_fields = ["heading", "artist__name"]
    inlines = [ChecklistEntryInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(entries_count=Count("entries"))

    @admin.display(description="公演数", ordering="entries_count")
    def entry_count(self, obj):
        return obj.entries_count

    def save_model(self, request, obj, form, change):
        if not change and obj.sort == 0:
            # 新しい見出しはページの先頭（新しいものが上）に置く
            current = m.ChecklistGroup.objects.filter(artist=obj.artist).aggregate(v=Min("sort"))["v"]
            if current is not None:
                obj.sort = current - SORT_STEP
        super().save_model(request, obj, form, change)


# ---- タスク（作業メモ） ----

class TaskVisibilityFilter(admin.SimpleListFilter):
    """一覧を開いたときは完了したタスクを出さない。「完了のみ」「すべて」に切り替えられる。"""
    title = "表示"
    parameter_name = "show"

    def lookups(self, request, model_admin):
        return [("done", "完了のみ"), ("all", "すべて")]

    def choices(self, changelist):
        # 何も選んでいないとき（最初の表示）を「未完了」として出す
        yield {"selected": self.value() is None,
               "query_string": changelist.get_query_string(remove=[self.parameter_name]),
               "display": "未完了（最初の表示）"}
        for lookup, title in self.lookup_choices:
            yield {"selected": self.value() == lookup,
                   "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                   "display": title}

    def queryset(self, request, queryset):
        if self.value() == "done":
            return queryset.filter(status="done")
        if self.value() == "all" or request.GET.get("status__exact"):
            # 「状態」の絞り込みで選んだときは、そちらに従う（「完了」を選んで何も出ないことがないように）
            return queryset
        return queryset.exclude(status="done")


@admin.register(m.Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "status", "priority", "updated"]
    list_editable = ["status", "priority"]
    list_filter = [TaskVisibilityFilter, "status", "category", "priority"]
    search_fields = ["title", "detail"]
    readonly_fields = ["created", "updated"]

    def get_queryset(self, request):
        # 完了したものは一覧の下に回す
        from django.db.models import Case, IntegerField, When
        return super().get_queryset(request).annotate(
            done_last=Case(When(status="done", then=1), default=0, output_field=IntegerField())
        ).order_by("done_last", "priority", "id")
