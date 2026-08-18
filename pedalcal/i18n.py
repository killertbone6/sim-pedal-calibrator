"""Interface translations.

Keys are the English strings themselves, so anything without a translation
falls back to readable English rather than to a missing-key placeholder.

Only interface chrome is translated. The console keeps the raw protocol
traffic in English - it exists for reporting faults, and a log that has been
translated is far harder to search for or to paste into an issue. Port names
and firmware messages stay as they come.

The translations live in one table with a column per language rather than in
a dictionary per language. That is not a style preference: with nine separate
dictionaries, adding a string means nine edits and a missing one shows up as a
stray English word in the middle of a German sentence. Here a row that is
short is a syntax error, and `check()` counts the rest.

These translations are mine, not a native speaker's. They cover short,
concrete interface words where that is a reasonable risk. If this ships
widely, it is worth having each column read over by someone who speaks it.
"""

from __future__ import annotations

#: Ordered as they appear in the language picker. The ten cover the countries
#: sim racing actually sells into.
LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
    ("pt", "Português (BR)"),
    ("it", "Italiano"),
    ("pl", "Polski"),
    ("nl", "Nederlands"),
    ("ru", "Русский"),
    ("ja", "日本語"),
]

LANGUAGE_CODES = [code for code, _name in LANGUAGES]

#: The order of the columns in every row of the table below.
COLUMNS = ("de", "fr", "es", "pt", "it", "pl", "nl", "ru", "ja")


def language_name(code: str) -> str:
    for candidate, name in LANGUAGES:
        if candidate == code:
            return name
    return code


# English source                                   de, fr, es, pt, it, pl, nl, ru, ja
ROWS: dict[str, tuple[str, ...]] = {
    # -- pedals ---------------------------------------------------------
    "Throttle": (
        "Gas", "Accélérateur", "Acelerador", "Acelerador", "Acceleratore",
        "Gaz", "Gas", "Газ", "アクセル"),
    "Brake": (
        "Bremse", "Frein", "Freno", "Freio", "Freno",
        "Hamulec", "Rem", "Тормоз", "ブレーキ"),
    "Clutch": (
        "Kupplung", "Embrayage", "Embrague", "Embreagem", "Frizione",
        "Sprzęgło", "Koppeling", "Сцепление", "クラッチ"),

    # -- chrome ---------------------------------------------------------
    "Pedal Calibrator": (
        "Pedal-Kalibrierung", "Calibrateur de pédales",
        "Calibrador de pedales", "Calibrador de pedais",
        "Calibratore pedali", "Kalibrator pedałów", "Pedaalkalibratie",
        "Калибратор педалей", "ペダルキャリブレーター"),
    "Calibration": (
        "Kalibrierung", "Étalonnage", "Calibración", "Calibração",
        "Calibrazione", "Kalibracja", "Kalibratie", "Калибровка",
        "キャリブレーション"),
    "Settings": (
        "Einstellungen", "Paramètres", "Ajustes", "Configurações",
        "Impostazioni", "Ustawienia", "Instellingen", "Настройки", "設定"),
    "Console": (
        "Konsole", "Console", "Consola", "Console", "Console",
        "Konsola", "Console", "Консоль", "コンソール"),

    # -- buttons --------------------------------------------------------
    "Min": ("Min", "Min", "Mín", "Mín", "Min", "Min", "Min", "Мин", "最小"),
    "Max": ("Max", "Max", "Máx", "Máx", "Max", "Maks", "Max", "Макс", "最大"),
    "Learn": (
        "Lernen", "Apprendre", "Aprender", "Aprender", "Apprendi",
        "Ucz", "Leren", "Обучить", "学習"),
    "Stop": (
        "Stopp", "Arrêter", "Parar", "Parar", "Ferma",
        "Stop", "Stoppen", "Стоп", "停止"),
    "Apply": (
        "Anwenden", "Appliquer", "Aplicar", "Aplicar", "Applica",
        "Zastosuj", "Toepassen", "Применить", "適用"),
    "Save": (
        "Speichern", "Enregistrer", "Guardar", "Salvar", "Salva",
        "Zapisz", "Opslaan", "Сохранить", "保存"),
    "Save as": (
        "Speichern unter", "Enregistrer sous", "Guardar como", "Salvar como",
        "Salva come", "Zapisz jako", "Opslaan als", "Сохранить как",
        "名前を付けて保存"),
    "Delete": (
        "Löschen", "Supprimer", "Eliminar", "Excluir", "Elimina",
        "Usuń", "Verwijderen", "Удалить", "削除"),
    "Reset": (
        "Zurücksetzen", "Réinitialiser", "Restablecer", "Redefinir",
        "Reimposta", "Resetuj", "Herstellen", "Сброс", "リセット"),
    "Reload": (
        "Neu laden", "Recharger", "Recargar", "Recarregar", "Ricarica",
        "Wczytaj ponownie", "Herladen", "Перезагрузить", "再読み込み"),
    "Linear": (
        "Linear", "Linéaire", "Lineal", "Linear", "Lineare",
        "Liniowa", "Lineair", "Линейно", "リニア"),
    "Use": (
        "Übernehmen", "Utiliser", "Usar", "Usar", "Usa",
        "Użyj", "Gebruiken", "Применить", "適用"),
    "Slider": (
        "Regler", "Curseur", "Deslizador", "Controle", "Cursore",
        "Suwak", "Schuifregelaar", "Ползунок", "スライダー"),
    "Cancel": (
        "Abbrechen", "Annuler", "Cancelar", "Cancelar", "Annulla",
        "Anuluj", "Annuleren", "Отмена", "キャンセル"),
    "Connect": (
        "Verbinden", "Connecter", "Conectar", "Conectar", "Connetti",
        "Połącz", "Verbinden", "Подключить", "接続"),
    "Disconnect": (
        "Trennen", "Déconnecter", "Desconectar", "Desconectar", "Disconnetti",
        "Rozłącz", "Verbreken", "Отключить", "切断"),
    "Refresh": (
        "Aktualisieren", "Actualiser", "Actualizar", "Atualizar", "Aggiorna",
        "Odśwież", "Vernieuwen", "Обновить", "更新"),
    "Reset everything": (
        "Alles zurücksetzen", "Tout réinitialiser", "Restablecer todo",
        "Redefinir tudo", "Reimposta tutto", "Zresetuj wszystko",
        "Alles herstellen", "Сбросить всё", "すべてリセット"),
    "Reset everything?": (
        "Alles zurücksetzen?", "Tout réinitialiser ?", "¿Restablecer todo?",
        "Redefinir tudo?", "Reimpostare tutto?", "Zresetować wszystko?",
        "Alles herstellen?", "Сбросить всё?", "すべてリセットしますか？"),
    "Continue?": (
        "Fortfahren?", "Continuer ?", "¿Continuar?", "Continuar?",
        "Continuare?", "Kontynuować?", "Doorgaan?", "Продолжить?",
        "続行しますか？"),

    # -- pedal card -----------------------------------------------------
    "Advanced": (
        "Erweitert", "Avancé", "Avanzado", "Avançado", "Avanzate",
        "Zaawansowane", "Geavanceerd", "Дополнительно", "詳細"),
    "Smoothing": (
        "Glättung", "Lissage", "Suavizado", "Suavização", "Livellamento",
        "Wygładzanie", "Afvlakking", "Сглаживание", "スムージング"),
    "Linearity": (
        "Linearität", "Linéarité", "Linealidad", "Linearidade", "Linearità",
        "Liniowość", "Lineariteit", "Линейность", "リニアリティ"),
    "Deadzone": (
        "Totzone", "Zone morte", "Zona muerta", "Zona morta", "Zona morta",
        "Martwa strefa", "Dode zone", "Мёртвая зона", "デッドゾーン"),
    "Raw value": (
        "Rohwert", "Valeur brute", "Valor bruto", "Valor bruto",
        "Valore grezzo", "Wartość surowa", "Ruwe waarde", "Сырое значение",
        "生の値"),

    # -- profiles -------------------------------------------------------
    "Profile": (
        "Profil", "Profil", "Perfil", "Perfil", "Profilo",
        "Profil", "Profiel", "Профиль", "プロファイル"),
    "Profile name": (
        "Profilname", "Nom du profil", "Nombre del perfil", "Nome do perfil",
        "Nome del profilo", "Nazwa profilu", "Profielnaam", "Имя профиля",
        "プロファイル名"),
    "New profile": (
        "Neues Profil", "Nouveau profil", "Nuevo perfil", "Novo perfil",
        "Nuovo profilo", "Nowy profil", "Nieuw profiel", "Новый профиль",
        "新しいプロファイル"),
    "Profile saved": (
        "Profil gespeichert", "Profil enregistré", "Perfil guardado",
        "Perfil salvo", "Profilo salvato", "Zapisano profil",
        "Profiel opgeslagen", "Профиль сохранён", "プロファイルを保存しました"),
    "Profile deleted": (
        "Profil gelöscht", "Profil supprimé", "Perfil eliminado",
        "Perfil excluído", "Profilo eliminato", "Usunięto profil",
        "Profiel verwijderd", "Профиль удалён", "プロファイルを削除しました"),
    "None": (
        "Keins", "Aucun", "Ninguno", "Nenhum", "Nessuno",
        "Brak", "Geen", "Нет", "なし"),

    # -- settings -------------------------------------------------------
    "Device": (
        "Gerät", "Périphérique", "Dispositivo", "Dispositivo", "Dispositivo",
        "Urządzenie", "Apparaat", "Устройство", "デバイス"),
    "Pedals": (
        "Pedale", "Pédales", "Pedales", "Pedais", "Pedali",
        "Pedały", "Pedalen", "Педали", "ペダル"),
    "Pedals connected": (
        "Angeschlossene Pedale", "Pédales connectées", "Pedales conectados",
        "Pedais conectados", "Pedali collegati", "Podłączone pedały",
        "Aangesloten pedalen", "Подключённые педали", "接続中のペダル"),
    "Handbrake": (
        "Handbremse", "Frein à main", "Freno de mano", "Freio de mão",
        "Freno a mano", "Hamulec ręczny", "Handrem", "Ручной тормоз",
        "ハンドブレーキ"),
    "Language": (
        "Sprache", "Langue", "Idioma", "Idioma", "Lingua",
        "Język", "Taal", "Язык", "言語"),
    "Interface": (
        "Oberfläche", "Interface", "Interfaz", "Interface", "Interfaccia",
        "Interfejs", "Interface", "Интерфейс", "インターフェース"),
    "Layout": (
        "Anordnung", "Disposition", "Disposición", "Disposição",
        "Disposizione", "Układ", "Indeling", "Расположение", "レイアウト"),
    "Stacked": (
        "Untereinander", "Empilé", "Apilado", "Empilhado", "Impilati",
        "Jeden pod drugim", "Gestapeld", "Вертикально", "縦並び"),
    "Side by side": (
        "Nebeneinander", "Côte à côte", "Lado a lado", "Lado a lado",
        "Affiancati", "Obok siebie", "Naast elkaar", "Рядом", "横並び"),
    "Brightness": (
        "Helligkeit", "Luminosité", "Brillo", "Brilho", "Luminosità",
        "Jasność", "Helderheid", "Яркость", "明るさ"),
    "Colour": (
        "Farbe", "Couleur", "Color", "Cor", "Colore",
        "Kolor", "Kleur", "Цвет", "色"),
    "Accent": (
        "Akzentfarbe", "Accent", "Acento", "Destaque", "Accento",
        "Akcent", "Accent", "Акцент", "アクセント"),
    "Custom": (
        "Eigene", "Personnalisé", "Personalizado", "Personalizado",
        "Personalizzato", "Własny", "Aangepast", "Свой", "カスタム"),
    "Refresh rate": (
        "Bildrate", "Fréquence", "Frecuencia", "Taxa de atualização",
        "Frequenza", "Odświeżanie", "Verversingssnelheid",
        "Частота обновления", "リフレッシュレート"),
    "Always on top": (
        "Immer im Vordergrund", "Toujours au premier plan", "Siempre visible",
        "Sempre visível", "Sempre in primo piano", "Zawsze na wierzchu",
        "Altijd op voorgrond", "Поверх всех окон", "常に手前に表示"),
    "Running in the background": (
        "Im Hintergrund", "En arrière-plan", "En segundo plano",
        "Em segundo plano", "In background", "W tle", "Op de achtergrond",
        "В фоне", "バックグラウンド動作"),
    "Keep running in the tray": (
        "Im Infobereich weiterlaufen", "Continuer dans la zone de notification",
        "Seguir en la bandeja", "Continuar na bandeja",
        "Resta nell'area di notifica", "Działaj w zasobniku",
        "Actief houden in systeemvak", "Сворачивать в трей",
        "通知領域で実行を継続"),
    "Start minimised": (
        "Minimiert starten", "Démarrer réduit", "Iniciar minimizado",
        "Iniciar minimizado", "Avvia ridotto", "Uruchom zminimalizowany",
        "Geminimaliseerd starten", "Запускать свёрнутым", "最小化して起動"),
    "Start with Windows": (
        "Mit Windows starten", "Démarrer avec Windows", "Iniciar con Windows",
        "Iniciar com o Windows", "Avvia con Windows", "Uruchamiaj z Windows",
        "Starten met Windows", "Запускать с Windows", "Windows と同時に起動"),

    # -- states ---------------------------------------------------------
    "Live": (
        "Live", "En direct", "En vivo", "Ao vivo", "In diretta",
        "Na żywo", "Live", "Активно", "ライブ"),
    "Offline": (
        "Offline", "Hors ligne", "Sin conexión", "Offline", "Offline",
        "Offline", "Offline", "Не в сети", "オフライン"),
    "Not connected": (
        "Nicht verbunden", "Non connecté", "No conectado", "Não conectado",
        "Non connesso", "Nie połączono", "Niet verbonden", "Нет подключения",
        "未接続"),
    "Connected": (
        "Verbunden", "Connecté", "Conectado", "Conectado", "Connesso",
        "Połączono", "Verbonden", "Подключено", "接続済み"),
    "Opening": (
        "Öffne", "Ouverture", "Abriendo", "Abrindo", "Apertura",
        "Otwieranie", "Openen", "Открытие", "接続中"),
    "Could not open": (
        "Konnte nicht geöffnet werden", "Impossible d'ouvrir",
        "No se pudo abrir", "Não foi possível abrir", "Impossibile aprire",
        "Nie można otworzyć", "Kan niet openen", "Не удалось открыть",
        "開けませんでした"),
    "No port": (
        "Kein Anschluss", "Aucun port", "Sin puerto", "Sem porta",
        "Nessuna porta", "Brak portu", "Geen poort", "Нет порта",
        "ポートなし"),
    "On": ("Ein", "Activé", "Activado", "Ativado", "Attivo",
           "Wł.", "Aan", "Вкл.", "オン"),
    "Off": ("Aus", "Désactivé", "Desactivado", "Desativado", "Disattivo",
            "Wył.", "Uit", "Выкл.", "オフ"),
    "Rest": ("Ruhelage", "Repos", "Reposo", "Repouso", "Riposo",
             "Spoczynek", "Rust", "Покой", "休止"),
    "Full": ("Voll", "Fond", "Fondo", "Fundo", "Fondo",
             "Pełny", "Vol", "Полный", "全開"),
    "Active": (
        "Aktiv", "Actif", "Activo", "Ativo", "Attivo",
        "Aktywne", "Actief", "Активен", "有効"),
    "Not active": (
        "Nicht aktiv", "Inactif", "Inactivo", "Inativo", "Non attivo",
        "Nieaktywne", "Niet actief", "Не активен", "無効"),
    "Unknown until connected": (
        "Unbekannt bis zur Verbindung", "Inconnu tant qu'il n'est pas connecté",
        "Desconocido hasta conectar", "Desconhecido até conectar",
        "Sconosciuto fino alla connessione", "Nieznane do połączenia",
        "Onbekend tot verbinding", "Неизвестно до подключения",
        "接続するまで不明"),
    "Game controller output": (
        "Gamecontroller-Ausgabe", "Sortie manette de jeu",
        "Salida de mando de juego", "Saída de controle de jogo",
        "Uscita controller di gioco", "Wyjście kontrolera gier",
        "Gamecontroller-uitvoer", "Вывод игрового контроллера",
        "ゲームコントローラー出力"),

    # -- sentences ------------------------------------------------------
    "Choose your language": (
        "Sprache auswählen", "Choisissez votre langue", "Elige tu idioma",
        "Escolha seu idioma", "Scegli la lingua", "Wybierz język",
        "Kies je taal", "Выберите язык", "言語を選択"),
    "You can change this later in Settings.": (
        "Sie können dies später in den Einstellungen ändern.",
        "Vous pourrez changer cela plus tard dans les Paramètres.",
        "Puedes cambiarlo más tarde en Ajustes.",
        "Você pode alterar isso depois nas Configurações.",
        "Puoi cambiarla in seguito nelle Impostazioni.",
        "Możesz to zmienić później w Ustawieniach.",
        "Je kunt dit later wijzigen bij Instellingen.",
        "Это можно изменить позже в настройках.",
        "後から設定で変更できます。"),
    "Smoothing reduces jitter but makes pedals less accurate.": (
        "Glättung reduziert das Zittern, macht die Pedale aber ungenauer.",
        "Le lissage réduit les tremblements mais rend les pédales moins précises.",
        "El suavizado reduce el temblor pero hace los pedales menos precisos.",
        "A suavização reduz a oscilação, mas deixa os pedais menos precisos.",
        "Il livellamento riduce il tremolio ma rende i pedali meno precisi.",
        "Wygładzanie redukuje drgania, ale zmniejsza dokładność pedałów.",
        "Afvlakking vermindert trillen maar maakt de pedalen minder nauwkeurig.",
        "Сглаживание уменьшает дрожание, но снижает точность педалей.",
        "スムージングは震えを抑えますが、ペダルの精度は下がります。"),
    "Turn off any pedal you haven't wired up.": (
        "Schalte jedes Pedal aus, das nicht angeschlossen ist.",
        "Désactivez toute pédale que vous n'avez pas câblée.",
        "Desactiva cualquier pedal que no hayas conectado.",
        "Desative qualquer pedal que você não tenha ligado.",
        "Disattiva ogni pedale che non hai collegato.",
        "Wyłącz każdy pedał, którego nie podłączyłeś.",
        "Zet elk pedaal uit dat je niet hebt aangesloten.",
        "Отключите педали, которые не подключены.",
        "配線していないペダルはオフにしてください。"),
    "An unused input copies its neighbour and looks like a stuck pedal.": (
        "Ein unbenutzter Eingang übernimmt das Signal des Nachbarn und wirkt "
        "wie ein klemmendes Pedal.",
        "Une entrée inutilisée copie sa voisine et donne l'impression d'une "
        "pédale bloquée.",
        "Una entrada sin usar copia a su vecina y parece un pedal atascado.",
        "Uma entrada não usada copia a vizinha e parece um pedal travado.",
        "Un ingresso inutilizzato copia quello vicino e sembra un pedale "
        "bloccato.",
        "Nieużywane wejście kopiuje sąsiednie i wygląda jak zacięty pedał.",
        "Een ongebruikte ingang kopieert zijn buur en lijkt op een "
        "vastzittend pedaal.",
        "Неиспользуемый вход копирует соседний и выглядит как залипшая педаль.",
        "未使用の入力は隣の信号を拾い、ペダルが固着したように見えます。"),
    "Left of centre is more sensitive; right is gentler.": (
        "Links der Mitte reagiert empfindlicher, rechts sanfter.",
        "À gauche du centre, plus sensible ; à droite, plus doux.",
        "A la izquierda del centro es más sensible; a la derecha, más suave.",
        "À esquerda do centro é mais sensível; à direita, mais suave.",
        "A sinistra del centro è più sensibile; a destra è più morbido.",
        "Na lewo od środka jest czulej, na prawo łagodniej.",
        "Links van het midden is gevoeliger; rechts is zachter.",
        "Левее центра — чувствительнее, правее — мягче.",
        "中央より左は敏感に、右は穏やかになります。"),
    "Deadzone ignores the first part of the travel.": (
        "Die Totzone ignoriert den ersten Teil des Wegs.",
        "La zone morte ignore le début de la course.",
        "La zona muerta ignora la primera parte del recorrido.",
        "A zona morta ignora a primeira parte do curso.",
        "La zona morta ignora la prima parte della corsa.",
        "Martwa strefa pomija początek skoku.",
        "De dode zone negeert het eerste deel van de slag.",
        "Мёртвая зона игнорирует начало хода.",
        "デッドゾーンはストローク初期を無視します。"),
    "Handbrake support is not implemented yet.": (
        "Handbremsen-Unterstützung gibt es noch nicht.",
        "La prise en charge du frein à main n'existe pas encore.",
        "El soporte del freno de mano aún no está implementado.",
        "O suporte ao freio de mão ainda não foi implementado.",
        "Il supporto al freno a mano non è ancora implementato.",
        "Obsługa hamulca ręcznego nie jest jeszcze gotowa.",
        "Ondersteuning voor de handrem is er nog niet.",
        "Поддержка ручного тормоза ещё не реализована.",
        "ハンドブレーキ対応はまだ実装されていません。"),
    "The console keeps its English wording so faults stay searchable.": (
        "Die Konsole bleibt englisch, damit Fehlermeldungen auffindbar bleiben.",
        "La console reste en anglais pour que les erreurs restent trouvables.",
        "La consola se mantiene en inglés para poder buscar los fallos.",
        "O console permanece em inglês para que as falhas continuem "
        "pesquisáveis.",
        "La console resta in inglese così gli errori restano ricercabili.",
        "Konsola zostaje po angielsku, aby błędy dało się wyszukać.",
        "De console blijft Engels zodat fouten vindbaar blijven.",
        "Консоль остаётся на английском, чтобы ошибки можно было найти.",
        "障害を検索しやすくするため、コンソールは英語のままです。"),
    "Once calibrated, the board works on its own.": (
        "Einmal kalibriert arbeitet die Platine allein weiter.",
        "Une fois étalonnée, la carte fonctionne toute seule.",
        "Una vez calibrada, la placa funciona por sí sola.",
        "Depois de calibrada, a placa funciona sozinha.",
        "Una volta calibrata, la scheda funziona da sola.",
        "Po kalibracji płytka działa samodzielnie.",
        "Eenmaal gekalibreerd werkt het bordje zelfstandig.",
        "После калибровки плата работает сама по себе.",
        "一度キャリブレーションすれば、基板は単体で動作します。"),
    "A tray icon isn't available on this system.": (
        "Ein Infobereich-Symbol ist auf diesem System nicht verfügbar.",
        "Une icône de zone de notification n'est pas disponible sur ce système.",
        "En este sistema no hay icono de bandeja disponible.",
        "Não há ícone de bandeja disponível neste sistema.",
        "L'icona nell'area di notifica non è disponibile su questo sistema.",
        "Ikona w zasobniku nie jest dostępna w tym systemie.",
        "Een systeemvakpictogram is op dit systeem niet beschikbaar.",
        "Значок в трее недоступен в этой системе.",
        "このシステムでは通知領域アイコンを利用できません。"),
    "Start with login is Windows only.": (
        "Der Start bei der Anmeldung ist nur unter Windows möglich.",
        "Le démarrage à l'ouverture de session n'existe que sous Windows.",
        "El inicio con la sesión sólo existe en Windows.",
        "Iniciar com o login só existe no Windows.",
        "L'avvio all'accesso esiste solo su Windows.",
        "Uruchamianie przy logowaniu działa tylko w Windows.",
        "Starten bij aanmelden werkt alleen op Windows.",
        "Запуск при входе в систему работает только в Windows.",
        "ログイン時の起動は Windows のみです。"),
    "Windows would not let us change the startup entry.": (
        "Windows hat die Änderung des Autostart-Eintrags nicht zugelassen.",
        "Windows a refusé la modification de l'entrée de démarrage.",
        "Windows no permitió cambiar la entrada de inicio.",
        "O Windows não permitiu alterar a entrada de inicialização.",
        "Windows non ha permesso di modificare la voce di avvio.",
        "Windows nie pozwolił zmienić wpisu autostartu.",
        "Windows stond het wijzigen van de opstartvermelding niet toe.",
        "Windows не разрешила изменить запись автозапуска.",
        "Windows がスタートアップ項目の変更を許可しませんでした。"),
    "Closing the window will now leave it running.": (
        "Das Schließen des Fensters lässt die App nun weiterlaufen.",
        "Fermer la fenêtre laissera désormais l'application tourner.",
        "Cerrar la ventana ahora la deja en ejecución.",
        "Fechar a janela agora a deixa em execução.",
        "Chiudere la finestra ora la lascia in esecuzione.",
        "Zamknięcie okna zostawi teraz aplikację uruchomioną.",
        "Het venster sluiten laat de app nu doordraaien.",
        "Закрытие окна теперь оставит приложение работать.",
        "ウィンドウを閉じても実行を継続します。"),
    "Closing the window will now quit.": (
        "Das Schließen des Fensters beendet die App nun.",
        "Fermer la fenêtre quittera désormais l'application.",
        "Cerrar la ventana ahora cierra la aplicación.",
        "Fechar a janela agora encerra o aplicativo.",
        "Chiudere la finestra ora chiude l'applicazione.",
        "Zamknięcie okna zakończy teraz aplikację.",
        "Het venster sluiten sluit de app nu af.",
        "Закрытие окна теперь завершит приложение.",
        "ウィンドウを閉じると終了します。"),
    "Turn on \"keep running in the tray\" as well, or there is nothing to "
    "minimise into.": (
        "Schalte auch „Im Infobereich weiterlaufen“ ein, sonst gibt es nichts "
        "zum Minimieren.",
        "Activez aussi « Continuer dans la zone de notification », sinon il "
        "n'y a rien où réduire.",
        "Activa también «Seguir en la bandeja», o no habrá dónde minimizar.",
        "Ative também \"Continuar na bandeja\", senão não há para onde "
        "minimizar.",
        "Attiva anche \"Resta nell'area di notifica\", altrimenti non c'è "
        "dove ridurre.",
        "Włącz też „Działaj w zasobniku”, bo inaczej nie ma gdzie minimalizować.",
        "Zet ook \"Actief houden in systeemvak\" aan, anders is er niets om "
        "naar te minimaliseren.",
        "Включите также «Сворачивать в трей», иначе сворачивать некуда.",
        "「通知領域で実行を継続」も有効にしてください。最小化先がありません。"),
    "At least one pedal has to stay switched on.": (
        "Mindestens ein Pedal muss eingeschaltet bleiben.",
        "Au moins une pédale doit rester activée.",
        "Al menos un pedal debe permanecer activado.",
        "Pelo menos um pedal precisa continuar ligado.",
        "Almeno un pedale deve restare attivo.",
        "Przynajmniej jeden pedał musi pozostać włączony.",
        "Ten minste één pedaal moet aan blijven.",
        "Хотя бы одна педаль должна оставаться включённой.",
        "少なくとも 1 つのペダルは有効なままにしてください。"),
    "No serial port found. Plug the board in and press Refresh.": (
        "Kein serieller Anschluss gefunden. Platine anschließen und auf "
        "Aktualisieren drücken.",
        "Aucun port série trouvé. Branchez la carte et appuyez sur Actualiser.",
        "No se encontró ningún puerto serie. Conecta la placa y pulsa "
        "Actualizar.",
        "Nenhuma porta serial encontrada. Conecte a placa e pressione "
        "Atualizar.",
        "Nessuna porta seriale trovata. Collega la scheda e premi Aggiorna.",
        "Nie znaleziono portu szeregowego. Podłącz płytkę i naciśnij Odśwież.",
        "Geen seriële poort gevonden. Sluit het bordje aan en druk op "
        "Vernieuwen.",
        "Последовательный порт не найден. Подключите плату и нажмите «Обновить».",
        "シリアルポートが見つかりません。基板を接続して「更新」を押してください。"),
    "Connected, but no reply - is the firmware flashed?": (
        "Verbunden, aber keine Antwort – ist die Firmware aufgespielt?",
        "Connecté, mais aucune réponse – le micrologiciel est-il installé ?",
        "Conectado, pero sin respuesta: ¿está grabado el firmware?",
        "Conectado, mas sem resposta - o firmware foi gravado?",
        "Connesso, ma nessuna risposta: il firmware è stato caricato?",
        "Połączono, ale brak odpowiedzi – czy wgrano firmware?",
        "Verbonden, maar geen antwoord - is de firmware geflasht?",
        "Подключено, но ответа нет — прошивка загружена?",
        "接続しましたが応答がありません。ファームウェアは書き込み済みですか？"),
    "Did not open - pick a port in Settings.": (
        "Ließ sich nicht öffnen – wähle einen Anschluss in den Einstellungen.",
        "Ouverture impossible – choisissez un port dans les Paramètres.",
        "No se pudo abrir: elige un puerto en Ajustes.",
        "Não abriu - escolha uma porta em Configurações.",
        "Non si è aperta: scegli una porta nelle Impostazioni.",
        "Nie udało się otworzyć – wybierz port w Ustawieniach.",
        "Kon niet openen - kies een poort bij Instellingen.",
        "Не открылось — выберите порт в настройках.",
        "開けませんでした。設定でポートを選んでください。"),
    "this board can't act as one, or the Joystick library wasn't installed "
    "when you flashed it. Calibration still works.": (
        "diese Platine kann das nicht, oder die Joystick-Bibliothek fehlte "
        "beim Aufspielen. Die Kalibrierung funktioniert trotzdem.",
        "cette carte n'en est pas capable, ou la bibliothèque Joystick "
        "manquait lors du flash. L'étalonnage fonctionne quand même.",
        "esta placa no puede serlo, o la biblioteca Joystick no estaba "
        "instalada al grabarla. La calibración sigue funcionando.",
        "esta placa não consegue, ou a biblioteca Joystick não estava "
        "instalada na gravação. A calibração continua funcionando.",
        "questa scheda non può farlo, oppure la libreria Joystick non era "
        "installata al momento del caricamento. La calibrazione funziona "
        "comunque.",
        "ta płytka tego nie potrafi albo biblioteki Joystick nie było przy "
        "wgrywaniu. Kalibracja nadal działa.",
        "dit bordje kan dat niet, of de Joystick-bibliotheek ontbrak bij het "
        "flashen. Kalibreren werkt nog steeds.",
        "эта плата так не умеет, либо при прошивке не была установлена "
        "библиотека Joystick. Калибровка всё равно работает.",
        "この基板は対応していないか、書き込み時に Joystick ライブラリが"
        "入っていませんでした。キャリブレーションは引き続き使えます。"),
    "Press it fully, then press Stop.": (
        "Ganz durchtreten, dann Stopp drücken.",
        "Enfoncez-la à fond, puis appuyez sur Arrêter.",
        "Písalo a fondo y luego pulsa Parar.",
        "Pressione até o fim e depois toque em Parar.",
        "Premilo a fondo, poi premi Ferma.",
        "Wciśnij do końca, potem naciśnij Stop.",
        "Trap hem volledig in en druk daarna op Stoppen.",
        "Нажмите до упора, затем нажмите «Стоп».",
        "最後まで踏み込んでから「停止」を押してください。"),
    "Nothing moved, range unchanged.": (
        "Nichts bewegt, Bereich unverändert.",
        "Rien n'a bougé, plage inchangée.",
        "Nada se movió, rango sin cambios.",
        "Nada se moveu, faixa inalterada.",
        "Niente si è mosso, intervallo invariato.",
        "Nic się nie poruszyło, zakres bez zmian.",
        "Niets bewoog, bereik ongewijzigd.",
        "Ничего не двигалось, диапазон не изменён.",
        "動きがなかったため範囲は変わりません。"),
    "Rest has to be below full - set Max at the floor first": (
        "Die Ruhelage muss unter Voll liegen – setze zuerst Max am Boden",
        "Le repos doit être sous le fond – réglez d'abord Max au plancher",
        "El reposo debe estar por debajo del fondo: fija primero Máx a fondo",
        "O repouso precisa ficar abaixo do fundo - defina Máx no fundo primeiro",
        "Il riposo deve stare sotto il fondo: imposta prima Max a fondo corsa",
        "Spoczynek musi być poniżej pełnego – najpierw ustaw Maks przy podłodze",
        "Rust moet onder vol liggen - stel eerst Max in op de bodem",
        "Покой должен быть ниже полного — сначала задайте «Макс» в полу",
        "休止位置は全開より下である必要があります。先に踏み切った状態で"
        "「最大」を設定してください"),
    "Full has to be above rest - set Min with your foot off first": (
        "Voll muss über der Ruhelage liegen – setze zuerst Min mit dem Fuß daneben",
        "Le fond doit être au-dessus du repos – réglez d'abord Min pied levé",
        "El fondo debe estar por encima del reposo: fija primero Mín con el "
        "pie fuera",
        "O fundo precisa ficar acima do repouso - defina Mín com o pé fora "
        "primeiro",
        "Il fondo deve stare sopra il riposo: imposta prima Min a piede "
        "sollevato",
        "Pełny musi być powyżej spoczynku – najpierw ustaw Min ze stopą poza "
        "pedałem",
        "Vol moet boven rust liggen - stel eerst Min in met je voet eraf",
        "Полное должно быть выше покоя — сначала задайте «Мин» с убранной ногой",
        "全開は休止位置より上である必要があります。先に足を離した状態で"
        "「最小」を設定してください"),
    "Calibration applied (not yet saved).": (
        "Kalibrierung angewendet (noch nicht gespeichert).",
        "Étalonnage appliqué (pas encore enregistré).",
        "Calibración aplicada (aún sin guardar).",
        "Calibração aplicada (ainda não salva).",
        "Calibrazione applicata (non ancora salvata).",
        "Zastosowano kalibrację (jeszcze niezapisaną).",
        "Kalibratie toegepast (nog niet opgeslagen).",
        "Калибровка применена (ещё не сохранена).",
        "キャリブレーションを適用しました（未保存）。"),
    "Saved to the device.": (
        "Auf dem Gerät gespeichert.",
        "Enregistré sur le périphérique.",
        "Guardado en el dispositivo.",
        "Salvo no dispositivo.",
        "Salvato sul dispositivo.",
        "Zapisano w urządzeniu.",
        "Opgeslagen op het apparaat.",
        "Сохранено на устройстве.",
        "デバイスに保存しました。"),
    "Everything reset to defaults.": (
        "Alles auf die Standardwerte zurückgesetzt.",
        "Tout est revenu aux valeurs par défaut.",
        "Todo restablecido a los valores predeterminados.",
        "Tudo redefinido para os padrões.",
        "Tutto reimpostato ai valori predefiniti.",
        "Wszystko przywrócono do ustawień domyślnych.",
        "Alles teruggezet naar de standaardwaarden.",
        "Всё сброшено к настройкам по умолчанию.",
        "すべて既定値にリセットしました。"),
    "Reset to defaults.": (
        "Auf Standard zurückgesetzt.",
        "Réinitialisé par défaut.",
        "Restablecido a valores predeterminados.",
        "Redefinido para os padrões.",
        "Reimpostato ai valori predefiniti.",
        "Przywrócono ustawienia domyślne.",
        "Teruggezet naar standaard.",
        "Сброшено к значениям по умолчанию.",
        "既定値にリセットしました。"),
    "Hex (#101418) or RGB (16, 20, 24).": (
        "Hex (#101418) oder RGB (16, 20, 24).",
        "Hex (#101418) ou RVB (16, 20, 24).",
        "Hex (#101418) o RGB (16, 20, 24).",
        "Hex (#101418) ou RGB (16, 20, 24).",
        "Hex (#101418) o RGB (16, 20, 24).",
        "Hex (#101418) lub RGB (16, 20, 24).",
        "Hex (#101418) of RGB (16, 20, 24).",
        "Hex (#101418) или RGB (16, 20, 24).",
        "16 進数 (#101418) または RGB (16, 20, 24)。"),
    "Hex (#22d3ee) or RGB (34, 211, 238).": (
        "Hex (#22d3ee) oder RGB (34, 211, 238).",
        "Hex (#22d3ee) ou RVB (34, 211, 238).",
        "Hex (#22d3ee) o RGB (34, 211, 238).",
        "Hex (#22d3ee) ou RGB (34, 211, 238).",
        "Hex (#22d3ee) o RGB (34, 211, 238).",
        "Hex (#22d3ee) lub RGB (34, 211, 238).",
        "Hex (#22d3ee) of RGB (34, 211, 238).",
        "Hex (#22d3ee) или RGB (34, 211, 238).",
        "16 進数 (#22d3ee) または RGB (34, 211, 238)。"),
    "Not a colour - try #101418 or 16, 20, 24.": (
        "Keine Farbe – versuche #101418 oder 16, 20, 24.",
        "Pas une couleur – essayez #101418 ou 16, 20, 24.",
        "No es un color: prueba #101418 o 16, 20, 24.",
        "Não é uma cor - tente #101418 ou 16, 20, 24.",
        "Non è un colore: prova #101418 o 16, 20, 24.",
        "To nie kolor – spróbuj #101418 albo 16, 20, 24.",
        "Geen kleur - probeer #101418 of 16, 20, 24.",
        "Это не цвет — попробуйте #101418 или 16, 20, 24.",
        "色ではありません。#101418 または 16, 20, 24 を試してください。"),
    "Not a colour - try #22d3ee or 34, 211, 238.": (
        "Keine Farbe – versuche #22d3ee oder 34, 211, 238.",
        "Pas une couleur – essayez #22d3ee ou 34, 211, 238.",
        "No es un color: prueba #22d3ee o 34, 211, 238.",
        "Não é uma cor - tente #22d3ee ou 34, 211, 238.",
        "Non è un colore: prova #22d3ee o 34, 211, 238.",
        "To nie kolor – spróbuj #22d3ee albo 34, 211, 238.",
        "Geen kleur - probeer #22d3ee of 34, 211, 238.",
        "Это не цвет — попробуйте #22d3ee или 34, 211, 238.",
        "色ではありません。#22d3ee または 34, 211, 238 を試してください。"),
    "This restores the defaults: calibration back to 0% - 100% on every "
    "pedal, all three pedals switched back on, the dark background with the "
    "cyan accent, always-on-top back on and the console hidden. Saved "
    "profiles are deleted. If a device is connected the reset is written to "
    "it as well.": (
        "Dies stellt die Standardwerte wieder her: Kalibrierung zurück auf "
        "0 % – 100 % bei jedem Pedal, alle drei Pedale wieder eingeschaltet, "
        "dunkler Hintergrund mit türkisem Akzent, „immer im Vordergrund“ "
        "wieder an und die Konsole ausgeblendet. Gespeicherte Profile werden "
        "gelöscht. Ist ein Gerät verbunden, wird der Reset auch dorthin "
        "geschrieben.",
        "Ceci rétablit les valeurs par défaut : étalonnage remis à 0 % – "
        "100 % sur chaque pédale, les trois pédales réactivées, fond sombre "
        "avec accent cyan, « toujours au premier plan » réactivé et console "
        "masquée. Les profils enregistrés sont supprimés. Si un périphérique "
        "est connecté, la réinitialisation lui est également écrite.",
        "Esto restaura los valores predeterminados: calibración de nuevo a "
        "0 % – 100 % en cada pedal, los tres pedales activados otra vez, "
        "fondo oscuro con acento cian, «siempre visible» de nuevo activo y la "
        "consola oculta. Los perfiles guardados se eliminan. Si hay un "
        "dispositivo conectado, el restablecimiento también se escribe en él.",
        "Isto restaura os padrões: calibração de volta a 0% – 100% em cada "
        "pedal, os três pedais ligados novamente, fundo escuro com destaque "
        "ciano, \"sempre visível\" ligado e o console oculto. Os perfis "
        "salvos são excluídos. Se houver um dispositivo conectado, a "
        "redefinição também é gravada nele.",
        "Questo ripristina i valori predefiniti: calibrazione di nuovo a "
        "0% – 100% su ogni pedale, tutti e tre i pedali riattivati, sfondo "
        "scuro con accento ciano, \"sempre in primo piano\" riattivato e "
        "console nascosta. I profili salvati vengono eliminati. Se un "
        "dispositivo è connesso, il ripristino viene scritto anche su di esso.",
        "To przywraca ustawienia domyślne: kalibrację z powrotem na "
        "0% – 100% dla każdego pedału, wszystkie trzy pedały włączone, ciemne "
        "tło z turkusowym akcentem, „zawsze na wierzchu” włączone i ukrytą "
        "konsolę. Zapisane profile zostaną usunięte. Jeśli urządzenie jest "
        "podłączone, reset zostanie zapisany także w nim.",
        "Dit herstelt de standaardwaarden: kalibratie terug naar 0% – 100% op "
        "elk pedaal, alle drie de pedalen weer aan, donkere achtergrond met "
        "cyaan accent, \"altijd op voorgrond\" weer aan en de console "
        "verborgen. Opgeslagen profielen worden verwijderd. Als er een "
        "apparaat is verbonden, wordt de reset ook daarnaartoe geschreven.",
        "Это вернёт настройки по умолчанию: калибровку к 0 % – 100 % на "
        "каждой педали, все три педали снова включены, тёмный фон с "
        "бирюзовым акцентом, «поверх всех окон» снова включено и консоль "
        "скрыта. Сохранённые профили будут удалены. Если устройство "
        "подключено, сброс запишется и в него.",
        "既定値に戻します。すべてのペダルのキャリブレーションを 0% – 100% に、"
        "3 つのペダルをすべて有効に、背景を暗くアクセントをシアンに、"
        "「常に手前に表示」を有効に、コンソールを非表示にします。"
        "保存済みプロファイルは削除されます。デバイスが接続されている場合は、"
        "リセットが書き込まれます。"),
}


def _build() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {code: {} for code in COLUMNS}
    for source, translations in ROWS.items():
        if len(translations) != len(COLUMNS):
            raise ValueError(
                f"{source!r} has {len(translations)} translations, "
                f"expected {len(COLUMNS)}")
        for code, translated in zip(COLUMNS, translations):
            catalog[code][source] = translated
    return catalog


CATALOG = _build()

_current = "en"


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGE_CODES else "en"


def current() -> str:
    return _current


def t(text: str) -> str:
    """Translate an interface string, falling back to the English source."""
    if _current == "en":
        return text
    return CATALOG.get(_current, {}).get(text, text)


def missing(code: str) -> list[str]:
    """English strings this language has no translation for."""
    if code == "en":
        return []
    known = CATALOG.get(code, {})
    return [source for source in ROWS if source not in known]
