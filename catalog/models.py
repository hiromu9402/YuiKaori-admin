"""ゆいかおりデータベースのモデル。

公開用 JSON（song.json など）は exporter.py がこのモデルから書き出す。
各モデルの sort は書き出すときの並び順（昇順）で、取り込み時の順番を 1000 刻みで保存している。
"""
from django.core.validators import RegexValidator
from django.db import models

# 作詞・作曲・編曲など、複数の名前を1つの欄に入れるときの区切り
MULTI_SEP = " / "
WEEKDAYS = "月火水木金土日"


def split_multi(value):
    return [v.strip() for v in value.split(MULTI_SEP.strip()) if v.strip()] if value else []


class Artist(models.Model):
    name = models.CharField("名前", max_length=100, unique=True)
    css_class = models.CharField("表示用クラス", max_length=50, blank=True,
                                 help_text="公開ページで色分けに使う CSS クラス（例: artist1）")
    sort = models.IntegerField("並び順", default=0)

    class Meta:
        ordering = ["sort", "id"]
        verbose_name = verbose_name_plural = "アーティスト"

    def __str__(self):
        return self.name


class CD(models.Model):
    TYPES = [("single", "シングル"), ("album", "アルバム"), ("minialbum", "ミニアルバム"),
             ("digital", "配信"), ("compilation", "コンピレーション")]
    title = models.CharField("タイトル", max_length=200, unique=True)
    type = models.CharField("種別", max_length=20, choices=TYPES)
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, verbose_name="アーティスト")
    release_date = models.DateField("発売日")
    sort = models.IntegerField("並び順", default=0)

    class Meta:
        ordering = ["sort", "id"]
        verbose_name = verbose_name_plural = "CD"

    def __str__(self):
        return self.title


class Song(models.Model):
    title = models.CharField("曲名", max_length=200, unique=True)
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, null=True, blank=True,
                               verbose_name="アーティスト", help_text="カバー曲など楽曲一覧に載せない曲は空でよい")
    in_catalog = models.BooleanField("楽曲一覧に載せる", default=True,
                                     help_text="オフにするとセットリスト用の曲（カバーなど）として扱い、song.json には出さない")
    lyrics = models.CharField("作詞", max_length=200, blank=True, help_text=f"複数いるときは「{MULTI_SEP}」で区切る")
    music = models.CharField("作曲", max_length=200, blank=True, help_text=f"複数いるときは「{MULTI_SEP}」で区切る")
    arranger = models.CharField("編曲", max_length=200, blank=True, help_text=f"複数いるときは「{MULTI_SEP}」で区切る")
    length = models.CharField("長さ", max_length=10, blank=True, help_text="例: 4:31")
    utanet = models.CharField("歌ネットID", max_length=20, blank=True)
    mv = models.CharField("MV（YouTube ID）", max_length=50, blank=True)
    dance = models.CharField("ダンス動画", max_length=200, blank=True)
    video = models.CharField("ライブ映像（YouTube ID）", max_length=50, blank=True)
    other = models.CharField("その他リンク", max_length=200, blank=True)
    call = models.CharField("コール表", max_length=100, blank=True,
                            help_text="数字なら seesaa の記事番号、文字列ならはてなのエントリー名")
    info = models.TextField("備考", blank=True)
    cds = models.ManyToManyField(CD, through="SongCD", blank=True, verbose_name="収録CD")
    sort = models.IntegerField("並び順", default=0)

    class Meta:
        ordering = ["sort", "id"]
        verbose_name = verbose_name_plural = "曲"

    def __str__(self):
        return self.title


class SongCD(models.Model):
    song = models.ForeignKey(Song, on_delete=models.CASCADE, verbose_name="曲")
    cd = models.ForeignKey(CD, on_delete=models.PROTECT, verbose_name="CD")
    ord = models.PositiveIntegerField("順番", default=0)

    class Meta:
        ordering = ["ord", "id"]
        unique_together = [("song", "cd")]
        verbose_name = verbose_name_plural = "収録CD"

    def __str__(self):
        return f"{self.song} / {self.cd}"


class SongAlias(models.Model):
    alias = models.CharField("別表記", max_length=200, unique=True)
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name="aliases", verbose_name="曲")

    class Meta:
        ordering = ["alias"]
        verbose_name = verbose_name_plural = "曲名の別表記"

    def __str__(self):
        return f"{self.alias} → {self.song}"


class Tour(models.Model):
    title = models.CharField("ツアー名", max_length=200, unique=True)
    compare_artist = models.ForeignKey(
        Artist, on_delete=models.PROTECT, null=True, blank=True, verbose_name="比較ページのグループ",
        help_text="設定するとツアーセットリスト比較ページ（tour.html）の選択肢に、このアーティストのグループで表示する")
    compare_sort = models.IntegerField("比較ページでの並び順", default=0)
    compare_default = models.BooleanField("比較ページで最初に選ばれている", default=False)

    class Meta:
        ordering = ["title"]
        verbose_name = verbose_name_plural = "ツアー・シリーズ"

    def __str__(self):
        return self.title


live_id_validator = RegexValidator(r"^\d{10}$", "公演IDは「開催日8桁＋連番2桁」の10桁です（例: 2025112401）")


class Live(models.Model):
    id = models.CharField("公演ID", max_length=10, primary_key=True, validators=[live_id_validator])
    title = models.CharField("公演名", max_length=300)
    tour = models.ForeignKey(Tour, on_delete=models.PROTECT, null=True, blank=True, verbose_name="ツアー・シリーズ")
    date = models.DateField("開催日")
    venue = models.CharField("会場", max_length=200, blank=True)
    artists = models.ManyToManyField(Artist, through="LiveArtist", verbose_name="出演")
    sort = models.IntegerField("並び順", default=0)

    # セットリストを Web の情報と照合した記録（公開用の JSON には書き出さない）
    VERIFY_CHOICES = [
        ("", "未確認"),
        ("ok", "一致"),
        ("fixed", "修正済み"),
        ("partial", "一部のみ確認"),
        ("doubt", "要確認"),
        ("notfound", "情報なし"),
    ]
    verify_status = models.CharField("照合の状態", max_length=10, choices=VERIFY_CHOICES, blank=True, default="")
    verify_date = models.DateField("照合日", null=True, blank=True)
    verify_source = models.TextField("照合の出典", blank=True, help_text="URL や資料名を 1 行に 1 つ")
    verify_note = models.TextField("照合のメモ", blank=True)

    class Meta:
        ordering = ["sort", "id"]
        verbose_name = verbose_name_plural = "公演"

    def __str__(self):
        return f"{self.id} {self.title}"


class LiveArtist(models.Model):
    live = models.ForeignKey(Live, on_delete=models.CASCADE, verbose_name="公演")
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, verbose_name="アーティスト")
    ord = models.PositiveIntegerField("順番", default=0)

    class Meta:
        ordering = ["ord", "id"]
        unique_together = [("live", "artist")]
        verbose_name = verbose_name_plural = "出演アーティスト"

    def __str__(self):
        return str(self.artist)


class SetlistItem(models.Model):
    MAIN, ENCORE, WENCORE = "main", "encore", "wencore"
    SECTIONS = [(MAIN, "本編"), (ENCORE, "アンコール"), (WENCORE, "Wアンコール")]
    live = models.ForeignKey(Live, on_delete=models.CASCADE, related_name="setlist_items", verbose_name="公演")
    section = models.CharField("区分", max_length=10, choices=SECTIONS, default=MAIN)
    pos = models.PositiveIntegerField("曲順")
    sub_pos = models.PositiveIntegerField("メドレー内の順番", default=0, help_text="メドレーでなければ 0")
    song = models.ForeignKey(Song, on_delete=models.PROTECT, verbose_name="曲")

    class Meta:
        ordering = ["live", "section", "pos", "sub_pos"]
        unique_together = [("live", "section", "pos", "sub_pos")]
        verbose_name = verbose_name_plural = "セットリストの曲"

    def __str__(self):
        return f"{self.get_section_display()} {self.pos}{f'-{self.sub_pos}' if self.sub_pos else ''} {self.song}"


class Event(models.Model):
    date = models.DateField("日付")
    start_time = models.CharField("開始時刻", max_length=10, blank=True, help_text="例: 18:00（不明なら空、未定なら --:--）")
    class1 = models.CharField("大分類", max_length=50, blank=True)
    class2 = models.CharField("中分類", max_length=50, blank=True)
    class3 = models.CharField("小分類", max_length=50, blank=True)
    title = models.CharField("タイトル", max_length=300)
    title2 = models.CharField("サブタイトル", max_length=300, blank=True)
    prefecture = models.CharField("都道府県", max_length=20, blank=True)
    venue = models.CharField("会場", max_length=200, blank=True)
    sponsor = models.CharField("主催・放送局など", max_length=200, blank=True)
    info = models.TextField("備考", blank=True)
    live = models.ForeignKey(Live, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="events", verbose_name="セットリスト（公演）")
    artists = models.ManyToManyField(Artist, through="EventArtist", verbose_name="アーティスト")
    sort = models.IntegerField("並び順", default=0)

    class Meta:
        ordering = ["sort", "id"]
        verbose_name = verbose_name_plural = "イベント"

    def __str__(self):
        return f"{self.date} {self.title}"

    @property
    def weekday(self):
        return WEEKDAYS[self.date.weekday()]


class EventArtist(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, verbose_name="イベント")
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, verbose_name="アーティスト")
    ord = models.PositiveIntegerField("順番", default=0)

    class Meta:
        ordering = ["ord", "id"]
        unique_together = [("event", "artist")]
        verbose_name = verbose_name_plural = "イベントのアーティスト"

    def __str__(self):
        return str(self.artist)


class ChecklistGroup(models.Model):
    """未回収楽曲チェック（my*.html）の見出し。アーティストごとのページに並ぶ。"""
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, verbose_name="ページ（アーティスト）")
    heading = models.CharField("見出し", max_length=300)
    sort = models.IntegerField("並び順", default=0)

    class Meta:
        ordering = ["artist__sort", "sort", "id"]
        verbose_name = verbose_name_plural = "未回収チェックの見出し"

    def __str__(self):
        return f"[{self.artist}] {self.heading}"


class ChecklistEntry(models.Model):
    group = models.ForeignKey(ChecklistGroup, on_delete=models.CASCADE, related_name="entries", verbose_name="見出し")
    live = models.ForeignKey(Live, on_delete=models.CASCADE, related_name="checklist_entries", verbose_name="公演")
    label = models.CharField("表示名", max_length=300, help_text="チェックボックスの横に出す名前（例: 千葉公演）")
    sort = models.IntegerField("並び順", default=0)

    class Meta:
        ordering = ["group", "sort", "id"]
        unique_together = [("group", "live")]
        verbose_name = verbose_name_plural = "未回収チェックの公演"

    def __str__(self):
        return f"{self.group.heading} / {self.label}"
