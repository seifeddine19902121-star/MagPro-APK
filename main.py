from datetime import datetime, timedelta
from functools import partial
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.network.urlrequest import UrlRequest
from kivy.storage.jsonstore import JsonStore
from kivy.uix.image import AsyncImage, Image
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFillRoundFlatButton, MDFlatButton, MDFillRoundFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.list import OneLineListItem
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.snackbar import MDSnackbar
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar
import hashlib
import json
import logging
import os
import re
import threading
import urllib.parse
try:
    import websocket
except ImportError:
    websocket = None
DEFAULT_PORT = '5000'

class DataValidator:

    @staticmethod
    def validate_ip(ip_address):
        if not ip_address or not isinstance(ip_address, str):
            return False
        pattern = '^(\\d{1,3}\\.){3}\\d{1,3}$'
        if not re.match(pattern, ip_address):
            return False
        return True

    @staticmethod
    def validate_quantity(qty_text):
        try:
            qty = float(qty_text)
            if qty <= 0:
                raise ValueError('La quantité doit être positive.')
            return qty
        except (ValueError, TypeError):
            raise ValueError('Veuillez saisir une quantité valide.')

    @staticmethod
    def sanitize_note(note_text):
        if not note_text:
            return ''
        return str(note_text).replace('"', '').replace("'", '').strip()[:200]

class WebSocketManager:

    def __init__(self, server_ip, port, on_message_callback, on_connect_callback=None, on_disconnect_callback=None):
        self.server_ip = server_ip
        self.port = port
        self.on_message_callback = on_message_callback
        self.on_connect_callback = on_connect_callback
        self.on_disconnect_callback = on_disconnect_callback
        self.ws = None
        self.connected = False
        self.thread = None
        self.should_reconnect = True
        self.reconnect_delay = 5

    def connect(self):
        if websocket is None:
            logging.warning('Module Websocket manquant.')
            return False

        def _run():
            ws_url = f'ws://{self.server_ip}:{self.port}/ws'
            while self.should_reconnect:
                try:
                    self.ws = websocket.WebSocketApp(ws_url, on_open=self._on_open, on_message=self._on_message, on_error=self._on_error, on_close=self._on_close)
                    self.ws.run_forever()
                    if self.should_reconnect:
                        threading.Event().wait(self.reconnect_delay)
                except Exception as e:
                    logging.error(f'WS Connection error: {e}')
                    if self.should_reconnect:
                        threading.Event().wait(self.reconnect_delay)
        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()
        return True

    def _on_open(self, ws):
        self.connected = True
        logging.info('WS Connected')
        if self.on_connect_callback:
            Clock.schedule_once(lambda dt: self.on_connect_callback(), 0)

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if self.on_message_callback:
                Clock.schedule_once(lambda dt: self.on_message_callback(data), 0)
        except Exception as e:
            logging.error(f'WS Message Error: {e}')

    def _on_error(self, ws, error):
        logging.error(f'WS Error: {error}')
        self.connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        logging.info('WS Closed')
        if self.on_disconnect_callback:
            Clock.schedule_once(lambda dt: self.on_disconnect_callback(), 0)

    def disconnect(self):
        self.should_reconnect = False
        self.connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.ws = None

class ImageCacheManager:

    def __init__(self, base_dir, cache_dir_name='image_cache'):
        self.cache_dir = os.path.join(base_dir, cache_dir_name)
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def get_cache_path(self, url):
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            extension = os.path.splitext(url.split('?')[0])[1]
            if not extension or len(extension) > 5:
                extension = '.jpg'
            filename = f'{url_hash}{extension}'
            return os.path.join(self.cache_dir, filename)
        except Exception:
            return None

    def is_cached(self, url):
        path = self.get_cache_path(url)
        return path and os.path.exists(path)

class ProductCard(MDCard):

    def __init__(self, product, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.product = product
        self.app = app_ref
        self.orientation = 'vertical'
        self.padding = dp(0)
        self.size_hint = (1, None)
        self.height = dp(220)
        self.radius = [16]
        self.elevation = 3
        self.ripple_behavior = True
        self.image_box = MDBoxLayout(size_hint_y=0.75)
        img_src = product.get('image')
        try:
            price_display = int(float(product.get('price', 0)))
        except:
            price_display = 0
        if img_src:
            safe_filename = urllib.parse.quote(img_src)
            self.image_url = f'http://{self.app.server_ip}:{DEFAULT_PORT}/api/images/{safe_filename}'
            self.img_widget = Image(allow_stretch=True, keep_ratio=False, source='')
            self.image_box.add_widget(self.img_widget)
            self.load_image()
        else:
            self._add_placeholder()
        self.add_widget(self.image_box)
        text_box = MDBoxLayout(orientation='vertical', size_hint_y=0.25, padding=dp(5))
        prod_name = product.get('name', 'Inconnu')
        lbl_name = MDLabel(text=prod_name, halign='center', bold=True, font_style='Subtitle1', theme_text_color='Primary', size_hint_y=0.6, shorten=True)
        lbl_price = MDLabel(text=f'{price_display} DA', halign='center', theme_text_color='Custom', text_color=(0, 0.7, 0, 1), font_style='Body2', bold=True, size_hint_y=0.4)
        text_box.add_widget(lbl_name)
        text_box.add_widget(lbl_price)
        self.add_widget(text_box)

    def load_image(self):
        cache_manager = self.app.image_cache
        cache_path = cache_manager.get_cache_path(self.image_url)
        if cache_manager.is_cached(self.image_url):
            self.img_widget.source = cache_path
            self.img_widget.reload()
        else:
            self.img_widget.source = 'assets/loading.png' if os.path.exists('assets/loading.png') else ''
            UrlRequest(self.image_url, file_path=cache_path, on_success=self._on_image_downloaded, on_failure=self._on_image_error, on_error=self._on_image_error, timeout=5)

    def _on_image_downloaded(self, req, result):
        if self.img_widget:
            self.img_widget.source = req.file_path
            self.img_widget.reload()

    def _on_image_error(self, req, error):
        self.image_box.clear_widgets()
        self._add_placeholder()

    def _add_placeholder(self):
        self.image_box.clear_widgets()
        self.image_box.add_widget(MDIcon(icon='food', font_size='60sp', pos_hint={'center_x': 0.5, 'center_y': 0.5}, theme_text_color='Hint'))

    def on_release(self):
        self.app.open_add_note_dialog(self.product)

class CartItemCard(MDCard):

    def __init__(self, item, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self.app = app_ref
        self.orientation = 'horizontal'
        self.padding = dp(8)
        self.spacing = dp(10)
        self.size_hint_y = None
        self.height = dp(100)
        self.radius = [15]
        self.elevation = 1
        icon_box = MDBoxLayout(size_hint_x=None, width=dp(50), pos_hint={'center_y': 0.5})
        icon = MDIcon(icon='food-variant', font_size='32sp', theme_text_color='Custom', text_color=self.app.theme_cls.primary_color, pos_hint={'center_x': 0.5, 'center_y': 0.5})
        icon_box.add_widget(icon)
        self.add_widget(icon_box)
        details_box = MDBoxLayout(orientation='vertical', size_hint_x=0.5, pos_hint={'center_y': 0.5}, spacing=dp(2))
        name_lbl = MDLabel(text=item['name'], bold=True, font_style='Subtitle2', theme_text_color='Primary', size_hint_y=None, height=dp(20), shorten=True)
        details_box.add_widget(name_lbl)
        note_box = MDBoxLayout(orientation='horizontal', adaptive_height=True, spacing=dp(5))
        note_text = item.get('note', '') or '---'
        note_lbl = MDLabel(text=note_text, font_style='Caption', theme_text_color='Hint', size_hint_x=0.8, shorten=True)
        edit_note_btn = MDIconButton(icon='pencil-outline', icon_size='18sp', theme_text_color='Custom', text_color=self.app.theme_cls.primary_color, size_hint=(None, None), size=(dp(24), dp(24)), pos_hint={'center_y': 0.5}, on_release=lambda x: self.app.open_edit_note_dialog(self.item))
        note_box.add_widget(note_lbl)
        note_box.add_widget(edit_note_btn)
        details_box.add_widget(note_box)
        try:
            price_val = int(float(item['price']))
        except:
            price_val = 0
        price_lbl = MDLabel(text=f'{price_val} DA', bold=True, theme_text_color='Custom', text_color=(0, 0.6, 0, 1), font_style='Caption', size_hint_y=None, height=dp(20))
        details_box.add_widget(price_lbl)
        self.add_widget(details_box)
        actions_box = MDBoxLayout(size_hint_x=None, width=dp(110), pos_hint={'center_y': 0.5})
        qty_card = MDCard(size_hint=(None, None), size=(dp(105), dp(40)), radius=[12], md_bg_color=(0.95, 0.95, 0.95, 1), elevation=0, pos_hint={'center_y': 0.5})
        qty_layout = MDBoxLayout(orientation='horizontal', spacing=0, padding=0)
        btn_minus = MDIconButton(icon='minus', icon_size='16sp', theme_text_color='Custom', text_color=(0.9, 0.1, 0.1, 1), on_release=self.decrease_qty, pos_hint={'center_y': 0.5})
        self.lbl_qty = MDLabel(text=str(int(item['qty'])), halign='center', bold=True, font_style='Subtitle1', theme_text_color='Primary', pos_hint={'center_y': 0.5})
        btn_plus = MDIconButton(icon='plus', icon_size='16sp', theme_text_color='Custom', text_color=(0.1, 0.7, 0.2, 1), on_release=self.increase_qty, pos_hint={'center_y': 0.5})
        qty_layout.add_widget(btn_minus)
        qty_layout.add_widget(self.lbl_qty)
        qty_layout.add_widget(btn_plus)
        qty_card.add_widget(qty_layout)
        actions_box.add_widget(qty_card)
        self.add_widget(actions_box)

    def increase_qty(self, x):
        self.item['qty'] += 1
        self.lbl_qty.text = str(int(self.item['qty']))
        self.app.update_cart_totals_live()

    def decrease_qty(self, x):
        if self.item['qty'] > 1:
            self.item['qty'] -= 1
            self.lbl_qty.text = str(int(self.item['qty']))
            self.app.update_cart_totals_live()
        else:
            self.app.remove_from_cart(self.item)

class TableCard(MDCard):

    def __init__(self, table, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.table = table
        self.app = app_ref
        self.orientation = 'vertical'
        self.size_hint = (1, None)
        self.height = dp(140)
        self.radius = [12]
        self.elevation = 2
        self.ripple_behavior = True
        self._long_press_event = None
        self._long_press_triggered = False
        self.header_box = MDBoxLayout(size_hint_y=None, height=dp(35), padding=[5, 0], md_bg_color=(0, 0, 0, 0.1))
        self.lbl_name = MDLabel(text=table['name'], halign='center', bold=True, theme_text_color='Custom')
        self.header_box.add_widget(self.lbl_name)
        self.add_widget(self.header_box)
        self.body_box = MDBoxLayout(orientation='vertical', padding=10, spacing=5)
        self.add_widget(self.body_box)
        self.update_state(table)

    def on_sub_seat_click(self, seat_num):
        if self.app.move_mode:
            pass
        else:
            self.app.current_table = self.table
            self.app.open_seat_order(seat_num)

    def update_state(self, table):
        self.table = table
        status = table['status']
        occupied_seats = table.get('occupied_seats', [])
        if status == 'occupied':
            self.md_bg_color = (0.85, 0.3, 0.3, 1)
            is_group = 0 in occupied_seats
            if not is_group and occupied_seats:
                self.md_bg_color = (0.95, 0.95, 0.95, 1)
        elif status == 'reserved':
            self.md_bg_color = (1, 0.6, 0, 1)
        else:
            self.md_bg_color = (0.3, 0.7, 0.3, 1)
        text_color = (1, 1, 1, 1) if self.md_bg_color[0] != 0.95 else (0.2, 0.2, 0.2, 1)
        self.lbl_name.text_color = text_color
        self.body_box.clear_widgets()
        if status == 'occupied' and 0 not in occupied_seats and occupied_seats:
            try:
                chairs_count = int(table.get('chairs', 4))
            except:
                chairs_count = 4
            grid = MDGridLayout(cols=2, spacing=dp(5), padding=dp(5))
            for i in range(1, chairs_count + 1):
                is_busy = i in occupied_seats
                seat_color = (0.85, 0.3, 0.3, 1) if is_busy else (0.3, 0.7, 0.3, 1)
                seat_card = MDCard(md_bg_color=seat_color, radius=[4], elevation=0, ripple_behavior=True)
                seat_card.bind(on_release=lambda x, seat=i: self.on_sub_seat_click(seat))
                seat_card.add_widget(MDLabel(text=str(i), halign='center', valign='middle', theme_text_color='Custom', text_color=(1, 1, 1, 1), bold=True))
                grid.add_widget(seat_card)
            self.body_box.add_widget(grid)
        else:
            icon_name = 'table-furniture'
            if status == 'occupied':
                icon_name = 'silverware-fork-knife'
            elif status == 'reserved':
                icon_name = 'clock-outline'
            icon = MDIcon(icon=icon_name, theme_text_color='Custom', text_color=text_color, pos_hint={'center_x': 0.5}, font_size='40sp', halign='center')
            info_text = 'Libre'
            if status == 'occupied':
                try:
                    total = int(float(table.get('total', 0)))
                    info_text = f'{total} DA'
                except:
                    info_text = '0 DA'
            elif status == 'reserved':
                info_text = 'Réservé'
            lbl_info = MDLabel(text=info_text, halign='center', bold=True, theme_text_color='Custom', text_color=text_color, font_style='H5')
            self.body_box.add_widget(icon)
            self.body_box.add_widget(lbl_info)

    def on_press(self):
        self._long_press_triggered = False
        self._long_press_event = Clock.schedule_once(self._on_long_press, 0.8)
        super().on_press()

    def _on_long_press(self, dt):
        self._long_press_triggered = True
        self.app.initiate_move(self.table)

    def on_release(self):
        if self._long_press_event:
            Clock.unschedule(self._long_press_event)
            self._long_press_event = None
        if not self._long_press_triggered:
            self._handle_normal_tap()
        super().on_release()

    def _handle_normal_tap(self):
        if self.app.move_mode:
            self.app.process_destination_selection(self.table)
        else:
            self.app.stop_refresh()
            self.app.current_table = self.table
            occupied_seats = self.table.get('occupied_seats', [])
            if self.table['status'] == 'occupied' and 0 in occupied_seats:
                self.app.open_seat_order(0)
            elif self.table['status'] == 'occupied' and occupied_seats:
                self.app.show_chairs_dialog(self.table)
            else:
                self.app.show_chairs_dialog(self.table)

class RestaurantApp(MDApp):
    cart = []
    all_products = []
    current_table = None
    current_seat = 0
    server_ip = '192.168.1.100'
    current_user_name = 'ADMIN'
    refresh_event = None
    REFRESH_RATE = 5
    auth_token = None
    token_expiry = None
    TOKEN_LIFETIME = 480
    displayed_products_count = 0
    PRODUCTS_PER_PAGE = 20
    ws_manager = None
    image_cache = None
    table_widgets = {}
    request_pending = False
    move_mode = False
    move_source_data = None
    offline_store = None
    cache_store = None
    is_offline_mode = False
    dialog_chairs = None
    dialog_ip = None
    dialog_cart = None
    dialog_note = None
    dialog_edit_note = None
    dialog_move_select = None
    dialog_empty_options = None
    dialog_pending = None
    pending_list_container = None
    status_bar_box = None
    status_bar_label = None
    status_bar_timer = None
    btn_cart = None
    btn_reminder = None
    cart_area = None
    data_dir = ''

    def build(self):
        self.title = 'MagPro Mobile'
        self.theme_cls.primary_palette = 'Teal'
        self.theme_cls.primary_hue = '700'
        self.theme_cls.theme_style = 'Light'
        self.data_dir = self.user_data_dir
        self.offline_store = JsonStore(os.path.join(self.data_dir, 'pending_orders.json'))
        self.cache_store = JsonStore(os.path.join(self.data_dir, 'app_cache.json'))
        log_path = os.path.join(self.data_dir, 'magpro.log')
        logging.basicConfig(filename=log_path, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.store = JsonStore(os.path.join(self.data_dir, 'app_settings.json'))
        self.image_cache = ImageCacheManager(base_dir=self.data_dir)
        if self.store.exists('config'):
            self.server_ip = self.store.get('config')['ip']
        if self.store.exists('user'):
            self.current_user_name = self.store.get('user')['name']
        self.ws_manager = WebSocketManager(self.server_ip, DEFAULT_PORT, self.on_websocket_message, on_connect_callback=lambda: self.notify('Connecté au serveur', 'info'), on_disconnect_callback=lambda: self.notify('Connexion au serveur perdue', 'error'))
        root_layout = MDBoxLayout(orientation='vertical')
        self.screen_manager = MDScreenManager()
        root_layout.add_widget(self.screen_manager)
        self.status_bar_box = MDBoxLayout(size_hint_y=None, height=dp(40), md_bg_color=(0.2, 0.2, 0.2, 1), padding=[dp(10), 0])
        self.status_bar_label = MDLabel(text='Prêt', halign='center', valign='middle', theme_text_color='Custom', text_color=(1, 1, 1, 1), font_style='Subtitle1', bold=True)
        self.status_bar_box.add_widget(self.status_bar_label)
        root_layout.add_widget(self.status_bar_box)
        screen_login = MDScreen(name='login')
        background_layout = MDFloatLayout()
        top_bg = MDBoxLayout(size_hint=(1, 0.5), pos_hint={'top': 1}, md_bg_color=self.theme_cls.primary_color)
        background_layout.add_widget(top_bg)
        settings_btn = MDIconButton(icon='cog', theme_text_color='Custom', text_color=(1, 1, 1, 1), pos_hint={'top': 0.98, 'right': 0.98}, on_release=self.open_ip_settings)
        background_layout.add_widget(settings_btn)
        card_login = MDCard(orientation='vertical', size_hint=(0.85, None), height=dp(400), pos_hint={'center_x': 0.5, 'center_y': 0.5}, padding=dp(30), spacing=dp(20), radius=[20], elevation=10, md_bg_color=(1, 1, 1, 1))
        icon_box = MDBoxLayout(size_hint_y=None, height=dp(80), pos_hint={'center_x': 0.5})
        main_icon = MDIcon(icon='silverware-variant', font_size='70sp', theme_text_color='Custom', text_color=self.theme_cls.primary_color, pos_hint={'center_x': 0.5, 'center_y': 0.5})
        icon_box.add_widget(main_icon)
        card_login.add_widget(icon_box)
        title_label = MDLabel(text='MagPro Restaurant', halign='center', font_style='H5', theme_text_color='Primary', bold=True)
        card_login.add_widget(title_label)
        self.username_field = MDTextField(text=self.current_user_name, hint_text="Nom d'utilisateur", icon_right='account', mode='rectangle')
        self.password_field = MDTextField(hint_text='Mot de passe', icon_right='key', password=True, mode='rectangle')
        btn_login = MDFillRoundFlatButton(text='CONNEXION', font_size='18sp', size_hint_x=1, height=dp(50), on_release=self.do_login)
        card_login.add_widget(self.username_field)
        card_login.add_widget(self.password_field)
        card_login.add_widget(MDBoxLayout(size_hint_y=None, height=dp(10)))
        card_login.add_widget(btn_login)
        background_layout.add_widget(card_login)
        footer = MDLabel(text='MagPro v7.1.0.0 © 2026', halign='center', pos_hint={'bottom': 1, 'center_x': 0.5}, theme_text_color='Hint', font_style='Caption', size_hint_y=None, height=dp(30))
        background_layout.add_widget(footer)
        screen_login.add_widget(background_layout)
        self.screen_manager.add_widget(screen_login)
        screen_tables = MDScreen(name='tables')
        layout = MDBoxLayout(orientation='vertical')
        self.toolbar_tables = MDTopAppBar(title='Salles & Tables', right_action_items=[['cloud-sync-outline', lambda x: self.open_pending_orders_dialog()], ['refresh', lambda x: self.fetch_tables(manual=True)], ['logout', lambda x: self.logout()]], elevation=2)
        layout.add_widget(self.toolbar_tables)
        self.scroll_tables = MDScrollView()
        self.grid_tables = MDGridLayout(cols=2, padding=dp(15), spacing=dp(15), size_hint_y=None, adaptive_height=True)
        self.scroll_tables.add_widget(self.grid_tables)
        layout.add_widget(self.scroll_tables)
        screen_tables.add_widget(layout)
        self.screen_manager.add_widget(screen_tables)
        screen_order = MDScreen(name='order')
        layout_o = MDBoxLayout(orientation='vertical')
        self.toolbar_order = MDTopAppBar(title='Prise de commande', left_action_items=[['arrow-left', lambda x: self.go_back()]], elevation=2)
        layout_o.add_widget(self.toolbar_order)
        search_box = MDBoxLayout(padding=(15, 5, 15, 5), size_hint_y=None, height=dp(65))
        self.search_field = MDTextField(hint_text='Rechercher article...', mode='rectangle', icon_right='magnify')
        self.search_field.bind(text=self.filter_products_live)
        search_box.add_widget(self.search_field)
        layout_o.add_widget(search_box)
        scroll_p = MDScrollView()
        self.grid_products = MDGridLayout(cols=2, padding=dp(10), spacing=dp(10), size_hint_y=None, adaptive_height=True)
        scroll_p.add_widget(self.grid_products)
        layout_o.add_widget(scroll_p)
        self.cart_area = MDBoxLayout(orientation='horizontal', padding=15, spacing=10, size_hint_y=None, height=dp(80))
        self.btn_reminder = MDFillRoundFlatIconButton(text='RAPPEL', icon='bell-ring', font_size='16sp', md_bg_color=(0.9, 0.5, 0.2, 1), size_hint_x=0.35, on_release=self.send_reminder)
        self.btn_cart = MDFillRoundFlatButton(text='VOIR PANIER (0)', font_size='18sp', size_hint_x=0.65, on_release=self.show_cart)
        self.cart_area.add_widget(self.btn_cart)
        layout_o.add_widget(self.cart_area)
        screen_order.add_widget(layout_o)
        self.screen_manager.add_widget(screen_order)
        Clock.schedule_once(lambda dt: self.ws_manager.connect(), 1)
        return root_layout

    def toggle_reminder_button(self, show=False):
        if self.btn_reminder.parent:
            self.cart_area.remove_widget(self.btn_reminder)
        if self.btn_cart.parent:
            self.cart_area.remove_widget(self.btn_cart)
        if show:
            self.btn_cart.size_hint_x = 0.65
            self.btn_reminder.size_hint_x = 0.35
            self.cart_area.add_widget(self.btn_cart)
            self.cart_area.add_widget(self.btn_reminder)
        else:
            self.btn_cart.size_hint_x = 1.0
            self.cart_area.add_widget(self.btn_cart)

    def send_reminder(self, instance):
        if self.is_offline_mode:
            self.notify("Impossible d'envoyer un rappel en mode hors ligne", 'error')
            return
        data = {'table_id': self.current_table['id'], 'seat_number': self.current_seat, 'user_name': self.current_user_name}
        self.notify('Envoi du rappel en cours...', 'info')
        UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/remind_order', req_body=json.dumps(data), req_headers={'Content-type': 'application/json'}, method='POST', on_success=lambda r, res: self.notify('Rappel envoyé en cuisine avec succès 🔔', 'success'), on_failure=lambda r, e: self.notify("Échec de l'envoi du rappel", 'error'), on_error=lambda r, e: self.notify('Erreur de connexion', 'error'), timeout=5)

    def initiate_move(self, table_info):
        occupied_seats = table_info.get('occupied_seats', [])
        if not occupied_seats:
            self.notify('Impossible : La table est vide', 'warning')
            return
        if 0 in occupied_seats:
            self._start_move_mode(table_info, 0)
            return
        self._show_seat_selection_for_move(table_info, occupied_seats)

    def _show_seat_selection_for_move(self, table_info, occupied_seats):
        if self.dialog_move_select:
            self.dialog_move_select.dismiss()
        content = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=10)
        for seat in occupied_seats:
            btn = MDRaisedButton(text=f'Déplacer Chaise {seat}', size_hint_x=1, on_release=lambda x, s=seat: self._confirm_seat_selection(table_info, s))
            content.add_widget(btn)
        self.dialog_move_select = MDDialog(title=f"Transfert depuis {table_info['name']}", type='custom', content_cls=content, buttons=[MDFlatButton(text='ANNULER', on_release=lambda x: self.dialog_move_select.dismiss())])
        self.dialog_move_select.open()

    def _confirm_seat_selection(self, table_info, seat_num):
        if self.dialog_move_select:
            self.dialog_move_select.dismiss()
        self._start_move_mode(table_info, seat_num)

    def _start_move_mode(self, table_info, seat_num):
        self.move_mode = True
        self.move_source_data = {'table': table_info, 'seat': seat_num}
        what = 'la table' if seat_num == 0 else f'la chaise {seat_num}'
        self.notify(f"Déplacement de {what} de {table_info['name']}... Sélectionnez la destination", 'info')
        self.toolbar_tables.title = 'Mode Transfert...'
        self.toolbar_tables.md_bg_color = (0.9, 0.5, 0.2, 1)

    def process_destination_selection(self, dest_table):
        if not self.move_mode:
            return
        source = self.move_source_data['table']
        source_seat = self.move_source_data['seat']
        if source['id'] == dest_table['id']:
            self.notify('Erreur: Destination identique à la source', 'error')
            self.cancel_move()
            return
        dest_seats = dest_table.get('occupied_seats', [])
        if dest_seats:
            self.notify('Action refusée : La table de destination est occupée.', 'error')
            self.cancel_move()
            return
        self.show_empty_table_mode_dialog(source, source_seat, dest_table)

    def show_empty_table_mode_dialog(self, source, source_seat, dest_table):
        if self.dialog_empty_options:
            self.dialog_empty_options.dismiss()
        source_name = source['name']
        dest_name = dest_table['name']
        what = 'Tout' if source_seat == 0 else f'Chaise {source_seat}'
        content = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=15, padding=[0, 10, 0, 0])
        btn_entire = MDRaisedButton(text='TABLE ENTIÈRE (GROUPE)', md_bg_color=(0.2, 0.6, 0.8, 1), size_hint_x=1, on_release=lambda x: self._confirm_empty_choice(source, source_seat, dest_table, 0))
        btn_chair = MDRaisedButton(text='CHAISE INDIVIDUELLE', md_bg_color=(0.3, 0.7, 0.3, 1), size_hint_x=1, on_release=lambda x: self._confirm_empty_choice(source, source_seat, dest_table, 1))
        content.add_widget(btn_entire)
        content.add_widget(btn_chair)
        self.dialog_empty_options = MDDialog(title=f'Vers {dest_name} (Vide)', text=f'Comment voulez-vous installer {what} ?', type='custom', content_cls=content, buttons=[MDFlatButton(text='ANNULER', on_release=lambda x: self.dialog_empty_options.dismiss())])
        self.dialog_empty_options.open()

    def _confirm_empty_choice(self, source, source_seat, dest_table, chosen_target_seat):
        if self.dialog_empty_options:
            self.dialog_empty_options.dismiss()
        self.show_move_confirmation(source, source_seat, dest_table, target_seat=chosen_target_seat)

    def show_move_confirmation(self, source, source_seat, dest, target_seat=1):
        what = 'toute la table' if source_seat == 0 else f'la chaise {source_seat}'
        target_desc = 'Toute la table' if target_seat == 0 else 'Chaise individuelle'
        dialog = MDDialog(title='Confirmer le transfert', text=f"Transférer {what} de '{source['name']}' vers '{dest['name']}' ?\n\nMode Destination : {target_desc}", buttons=[MDFlatButton(text='NON', on_release=lambda x: self.cancel_move_dialog(dialog)), MDRaisedButton(text='OUI', on_release=lambda x: self.execute_move(source, source_seat, dest, dialog, target_seat))])
        dialog.open()

    def cancel_move_dialog(self, dialog):
        dialog.dismiss()
        self.cancel_move(show_notification=True)

    def cancel_move(self, show_notification=True):
        self.move_mode = False
        self.move_source_data = None
        if show_notification:
            self.notify('Transfert annulé', 'info')
        self.toolbar_tables.title = 'Salles & Tables'
        self.toolbar_tables.md_bg_color = self.theme_cls.primary_color

    def execute_move(self, source, source_seat, dest, dialog, target_seat=1):
        dialog.dismiss()
        if source_seat == 0 and target_seat == 0:
            url = f'http://{self.server_ip}:{DEFAULT_PORT}/api/move_table'
            data = {'source_id': source['id'], 'dest_id': dest['id']}
        else:
            url = f'http://{self.server_ip}:{DEFAULT_PORT}/api/move_seat'
            data = {'table_id': source['id'], 'source_seat': source_seat, 'dest_table_id': dest['id'], 'dest_seat': target_seat}
        UrlRequest(url, req_body=json.dumps(data), req_headers={'Content-type': 'application/json'}, method='POST', on_success=lambda r, res: self.on_move_success(res), on_failure=lambda r, e: self.notify('Échec du transfert', 'error'), on_error=lambda r, e: self.notify('Erreur de connexion', 'error'), timeout=5)

    def on_move_success(self, res):
        if res.get('status') == 'success':
            self.notify('Transfert effectué avec succès ✅', 'success')
        else:
            msg = res.get('message', 'Erreur lors du transfert')
            self.notify(msg, 'error')
        self.cancel_move(show_notification=False)
        self.fetch_tables()

    def notify(self, message, type='info'):
        if not self.status_bar_box:
            return
        colors = {'success': (0.1, 0.6, 0.2, 1), 'error': (0.75, 0.2, 0.2, 1), 'warning': (0.9, 0.6, 0.1, 1), 'info': (0.2, 0.4, 0.6, 1)}
        if self.status_bar_timer:
            self.status_bar_timer.cancel()
        self.status_bar_label.text = message
        self.status_bar_box.md_bg_color = colors.get(type, (0.2, 0.2, 0.2, 1))
        self.status_bar_timer = Clock.schedule_once(self.reset_status_bar, 4)

    def reset_status_bar(self, dt):
        if self.status_bar_box:
            self.status_bar_label.text = 'Prêt'
            self.status_bar_box.md_bg_color = (0.2, 0.2, 0.2, 1)

    def on_stop(self):
        if self.ws_manager:
            self.ws_manager.disconnect()

    def on_websocket_message(self, data):
        msg_type = data.get('type')
        if msg_type == 'tables_update':
            Clock.schedule_once(lambda dt: self.fetch_tables(), 0)

    def hash_password(self, password):
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def standard_error_handler(self, req, error, custom_msg=None, fatal=False):
        self.request_pending = False
        err_str = str(error).lower()
        msg = custom_msg or 'Erreur de connexion.'
        if 'connecttimeout' in err_str or 'etimedout' in err_str:
            msg = 'Le serveur ne répond pas (Délai dépassé).'
        elif 'connection refused' in err_str or 'econnrefused' in err_str:
            msg = "Connexion refusée. Vérifiez l'adresse IP."
        elif 'no route to host' in err_str or 'ehostunreach' in err_str:
            msg = 'Serveur introuvable. Vérifiez votre réseau Wi-Fi.'
        elif 'socket' in err_str:
            msg = 'Erreur réseau (Socket). Vérifiez la connexion.'
        logging.error(f'Network Error: {err_str}')
        if not fatal:
            self.notify(msg, 'error')
        else:
            self.show_fatal_error(msg)

    def show_fatal_error(self, msg):
        dialog = MDDialog(title='Erreur Critique', text=msg, buttons=[MDFlatButton(text='OK', on_release=lambda x: dialog.dismiss())])
        dialog.open()

    def open_ip_settings(self, instance=None):
        content = MDBoxLayout(orientation='vertical', spacing='12dp', size_hint_y=None, height='80dp')
        self.ip_field_dialog = MDTextField(text=self.server_ip, hint_text='Adresse IP Serveur', mode='rectangle')
        content.add_widget(self.ip_field_dialog)
        self.dialog_ip = MDDialog(title='Configuration Serveur', type='custom', content_cls=content, buttons=[MDFlatButton(text='ANNULER', on_release=lambda x: self.dialog_ip.dismiss()), MDRaisedButton(text='ENREGISTRER', on_release=self.save_ip_settings)])
        self.dialog_ip.open()

    def save_ip_settings(self, instance):
        new_ip = self.ip_field_dialog.text.strip()
        if not DataValidator.validate_ip(new_ip):
            self.notify('Format IP invalide.', 'error')
            return
        self.notify('Test de connexion en cours...', 'info')
        test_url = f'http://{new_ip}:{DEFAULT_PORT}/api/tables'
        UrlRequest(test_url, on_success=lambda req, res: self._on_ip_test_success(new_ip), on_failure=lambda req, res: self._on_ip_test_fail(), on_error=lambda req, err: self._on_ip_test_fail(), timeout=3)

    def _on_ip_test_success(self, new_ip):
        self.server_ip = new_ip
        self.store.put('config', ip=new_ip)
        if self.ws_manager:
            self.ws_manager.server_ip = new_ip
            self.ws_manager.disconnect()
            Clock.schedule_once(lambda dt: self.ws_manager.connect(), 1)
        self.notify('Connexion au serveur réussie.', 'success')
        if self.dialog_ip:
            self.dialog_ip.dismiss()
        self.fetch_tables(manual=True)

    def _on_ip_test_fail(self):
        self.notify("Échec de connexion. Vérifiez l'adresse IP.", 'error')

    def do_login(self, instance):
        username = self.username_field.text.strip()
        password = self.password_field.text.strip()
        if not username:
            self.notify("Nom d'utilisateur requis.", 'warning')
            return
        url = f'http://{self.server_ip}:{DEFAULT_PORT}/api/login'
        headers = {'Content-type': 'application/json'}
        body = json.dumps({'username': username, 'password': password})
        UrlRequest(url, req_body=body, req_headers=headers, method='POST', on_success=self.login_success_handler, on_failure=lambda r, e: self.notify('Identifiants incorrects.', 'error'), on_error=lambda r, e: self.standard_error_handler(r, e, 'Serveur de connexion inaccessible.'), timeout=5)

    def login_success_handler(self, req, result):
        if result.get('status') == 'success':
            self.current_user_name = self.username_field.text.strip()
            self.store.put('user', name=self.current_user_name)
            if 'token' in result:
                self.auth_token = result['token']
                self.token_expiry = datetime.now() + timedelta(minutes=self.TOKEN_LIFETIME)
            self.notify(f'Authentification réussie. Bienvenue {self.current_user_name}.', 'success')
            self.screen_manager.current = 'tables'
            self.fetch_tables()
            self.start_refresh()
        else:
            self.notify('Échec de la connexion.', 'error')

    def logout(self):
        self.stop_refresh()
        self.screen_manager.current = 'login'
        self.password_field.text = ''

    def start_refresh(self):
        self.stop_refresh()
        self.refresh_event = Clock.schedule_interval(self.silent_refresh, self.REFRESH_RATE)

    def stop_refresh(self):
        if self.refresh_event:
            self.refresh_event.cancel()
            self.refresh_event = None

    def fetch_tables(self, manual=False):
        if self.request_pending:
            return
        self.request_pending = True

        def on_success(req, result):
            self.is_offline_mode = False
            self.update_tables(req, result)
            self.cache_store.put('tables', data=result)
            self._cache_all_tables_details(result)
            self.process_offline_queue()

        def on_error(req, error):
            self.request_pending = False
            self.is_offline_mode = True
            logging.warning('Offline mode: Loading tables from cache')
            if self.cache_store.exists('tables'):
                cached_tables = self.cache_store.get('tables')['data']
                self.update_tables(None, cached_tables)
                if manual:
                    self.notify('Mode Hors Ligne : Données locales chargées.', 'warning')
            elif manual:
                self.standard_error_handler(req, error, "Impossible d'actualiser les tables.")
        UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/tables', on_success=on_success, on_error=on_error, on_failure=on_error, timeout=5)

    def _cache_all_tables_details(self, tables):
        for t in tables:
            tid = t['id']
            UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/table_seats/{tid}', on_success=lambda r, res, table_id=tid: self.cache_store.put(f'seats_{table_id}', data=res), on_error=self.silent_error, timeout=10)

    def silent_error(self, req, error):
        self.request_pending = False

    def silent_refresh(self, dt):
        pending_count = len(self.offline_store.keys())
        if pending_count > 0:
            if hasattr(self, 'toolbar_tables'):
                self.toolbar_tables.right_action_items[0] = ['cloud-sync-outline', lambda x: self.open_pending_orders_dialog()]
        if self.screen_manager.current == 'tables':
            if self.request_pending:
                return
            self.fetch_tables()

    def update_tables(self, req, result):
        self.request_pending = False
        try:
            sorted_tables = sorted(result, key=lambda x: x['name'])
            existing_ids = set(self.table_widgets.keys())
            new_ids = set((t['id'] for t in sorted_tables))
            for tid in existing_ids - new_ids:
                widget = self.table_widgets.pop(tid)
                if widget.parent:
                    self.grid_tables.remove_widget(widget)
            for t_data in sorted_tables:
                tid = t_data['id']
                if tid in self.table_widgets:
                    self.table_widgets[tid].update_state(t_data)
                else:
                    new_card = TableCard(t_data, self)
                    self.table_widgets[tid] = new_card
                    self.grid_tables.add_widget(new_card)
        except Exception as e:
            logging.error(f'Update tables error: {e}')

    def open_pending_orders_dialog(self):
        keys = list(self.offline_store.keys())
        if not keys:
            self.notify('Aucune commande en attente de synchronisation.', 'info')
            return
        self.pending_list_container = MDBoxLayout(orientation='vertical', adaptive_height=True)
        scroll = MDScrollView(size_hint_y=None, height=dp(300))
        scroll.add_widget(self.pending_list_container)
        self.refresh_pending_dialog_content()
        self.dialog_pending = MDDialog(title='Commandes Hors Ligne', type='custom', content_cls=scroll, buttons=[MDFlatButton(text='FERMER', on_release=lambda x: self.dialog_pending.dismiss())])
        self.dialog_pending.open()

    def refresh_pending_dialog_content(self):
        if not self.pending_list_container:
            return
        self.pending_list_container.clear_widgets()
        keys = list(self.offline_store.keys())
        if not keys:
            self.pending_list_container.add_widget(MDLabel(text='Toutes les commandes ont été synchronisées !', halign='center', theme_text_color='Hint'))
            return
        for key in keys:
            data = self.offline_store.get(key)['order_data']
            table_name = 'Table Inconnue'
            if self.cache_store.exists('tables'):
                tables = self.cache_store.get('tables')['data']
                for t in tables:
                    if t['id'] == data['table_id']:
                        table_name = t['name']
                        break
            seat_info = 'Groupe' if data['seat_number'] == 0 else f"Chaise {data['seat_number']}"
            total_price = sum((item['price'] * item['qty'] for item in data['items']))
            item_box = MDCard(orientation='horizontal', size_hint_y=None, height=dp(60), padding=dp(10), radius=[8], elevation=1, md_bg_color=(0.95, 0.95, 0.95, 1))
            info_layout = MDBoxLayout(orientation='vertical', size_hint_x=0.7)
            info_layout.add_widget(MDLabel(text=f'{table_name} - {seat_info}', bold=True, theme_text_color='Primary'))
            info_layout.add_widget(MDLabel(text=f"{len(data['items'])} articles | {int(total_price)} DA", theme_text_color='Secondary', font_style='Caption'))
            icon = MDIcon(icon='cloud-off-outline', theme_text_color='Custom', text_color=(0.8, 0.4, 0.4, 1), pos_hint={'center_y': 0.5})
            item_box.add_widget(info_layout)
            item_box.add_widget(icon)
            self.pending_list_container.add_widget(item_box)
            self.pending_list_container.add_widget(MDBoxLayout(size_hint_y=None, height=dp(5)))

    def show_chairs_dialog(self, table):
        self.current_table = table
        url = f"http://{self.server_ip}:{DEFAULT_PORT}/api/table_seats/{table['id']}"
        UrlRequest(url, on_success=lambda req, res: self._on_seats_loaded(table, res), on_error=lambda r, e: self._load_seats_offline(table), on_failure=lambda r, e: self._load_seats_offline(table), timeout=3)

    def _on_seats_loaded(self, table, res):
        self.cache_store.put(f"seats_{table['id']}", data=res)
        self._build_chairs_dialog(table, res)

    def _load_seats_offline(self, table):
        key = f"seats_{table['id']}"
        if self.cache_store.exists(key):
            data = self.cache_store.get(key)['data']
            self._build_chairs_dialog(table, data)
            self.notify('Mode Hors Ligne : Table ouverte.', 'warning')
        else:
            self.notify('Erreur : Données non disponibles hors ligne.', 'error')

    def _build_chairs_dialog(self, table, seats_status):
        if self.dialog_chairs:
            self.dialog_chairs.dismiss()
        self.current_table = table
        content = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(15), padding=[0, 10, 0, 0])
        occupied_individuals = [k for k in seats_status.keys() if k != '0']
        if not occupied_individuals:
            group_status = seats_status.get('0')
            group_bg = (0.9, 0.3, 0.3, 1) if group_status else (0.2, 0.6, 0.8, 1)
            try:
                amount = int(float(group_status['amount'])) if group_status else 0
            except:
                amount = 0
            group_txt = f'GROUPE\n{amount} DA' if group_status else 'GROUPE'
            card_group = MDCard(size_hint_y=None, height=dp(60), radius=[12], md_bg_color=group_bg, ripple_behavior=True, on_release=lambda x: self.open_seat_order(0))
            box_g = MDBoxLayout(orientation='horizontal', padding=10)
            box_g.add_widget(MDIcon(icon='account-group', theme_text_color='Custom', text_color=(1, 1, 1, 1), font_size='32sp', pos_hint={'center_y': 0.5}))
            box_g.add_widget(MDLabel(text=group_txt, halign='center', bold=True, theme_text_color='Custom', text_color=(1, 1, 1, 1), font_style='H6'))
            card_group.add_widget(box_g)
            content.add_widget(card_group)
            content.add_widget(MDBoxLayout(size_hint_y=None, height=1, md_bg_color=(0.8, 0.8, 0.8, 1)))
        grid_chairs = MDGridLayout(cols=2, spacing=dp(10), adaptive_height=True)
        try:
            chair_count = int(table.get('chairs', 4))
        except:
            chair_count = 4
        for i in range(1, chair_count + 1):
            s_stat = seats_status.get(str(i))
            is_busy = s_stat is not None
            c_color = (0.9, 0.3, 0.3, 1) if is_busy else (0.3, 0.7, 0.3, 1)
            try:
                amt = int(float(s_stat['amount'])) if is_busy else 0
            except:
                amt = 0
            c_text = f'{amt} DA' if is_busy else 'Libre'
            card = MDCard(size_hint_y=None, height=dp(80), radius=[10], md_bg_color=c_color, ripple_behavior=True, on_release=lambda x, seat=i: self.open_seat_order(seat))
            card_box = MDBoxLayout(orientation='vertical', padding=5)
            card_box.add_widget(MDIcon(icon='chair-school', theme_text_color='Custom', text_color=(1, 1, 1, 1), pos_hint={'center_x': 0.5}, font_size='24sp', halign='center'))
            card_box.add_widget(MDLabel(text=f'Chaise {i}', halign='center', bold=True, theme_text_color='Custom', text_color=(1, 1, 1, 1), font_style='Caption'))
            card_box.add_widget(MDLabel(text=c_text, halign='center', theme_text_color='Custom', text_color=(1, 1, 1, 1), font_style='Caption'))
            card.add_widget(card_box)
            grid_chairs.add_widget(card)
        content.add_widget(grid_chairs)
        self.dialog_chairs = MDDialog(title=f"Table: {table['name']}", type='custom', content_cls=content)
        self.dialog_chairs.open()

    def open_seat_order(self, seat_num):
        if self.current_table is None:
            self.notify('Erreur : Veuillez sélectionner la table à nouveau.', 'error')
            if self.dialog_chairs:
                self.dialog_chairs.dismiss()
            return
        if self.dialog_chairs:
            self.dialog_chairs.dismiss()
        self.current_seat = seat_num
        self.stop_refresh()
        self.cart = []
        self.update_cart_btn()
        occ_list = self.current_table.get('occupied_seats', [])
        occ_list_str = [str(x) for x in occ_list]
        is_seat_occupied = str(seat_num) in occ_list_str
        self.toggle_reminder_button(show=is_seat_occupied)
        seat_title = 'Groupe' if seat_num == 0 else f'Chaise {seat_num}'
        self.toolbar_order.title = f"{self.current_table['name']} - {seat_title}"
        self.screen_manager.current = 'order'
        self.search_field.text = ''
        self.load_products()
        if not self.is_offline_mode:
            UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/cart_details', req_body=json.dumps({'table_id': self.current_table['id'], 'seat_number': self.current_seat}), req_headers={'Content-type': 'application/json'}, method='POST', on_success=self.on_cart_loaded, on_error=self.silent_error, timeout=5)
        else:
            self.cart = []

    def on_cart_loaded(self, req, result):
        if result and isinstance(result, list):
            self.cart = result
        else:
            self.cart = []
        self.update_cart_btn()

    def load_products(self):

        def on_success(req, result):
            self.update_prods(req, result)
            self.cache_store.put('products', data=result)

        def on_error(req, error):
            if self.cache_store.exists('products'):
                cached_prods = self.cache_store.get('products')['data']
                self.update_prods(None, cached_prods)
                self.notify('Menu chargé localement.', 'info')
            else:
                self.standard_error_handler(req, error, 'Impossible de charger les produits.')
        UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/products', on_success=on_success, on_error=on_error, on_failure=on_error, timeout=5)

    def update_prods(self, req, result):
        self.all_products = result
        self.display_products(result)

    def display_products(self, products):
        self.grid_products.clear_widgets()
        self.displayed_products_count = 0
        self.current_products = products
        self._load_more_products()

    def _load_more_products(self):
        start = self.displayed_products_count
        end = start + self.PRODUCTS_PER_PAGE
        products_to_show = self.current_products[start:end]
        for p in products_to_show:
            self.grid_products.add_widget(ProductCard(p, self))
        self.displayed_products_count = end
        if end < len(self.current_products):
            remaining = len(self.current_products) - end
            load_more_card = MDCard(size_hint=(1, None), height=dp(60), radius=[15], elevation=2, md_bg_color=self.theme_cls.primary_color, ripple_behavior=True, on_release=lambda x: self._on_load_more_clicked())
            load_more_box = MDBoxLayout(orientation='horizontal', padding=10, spacing=10)
            load_more_box.add_widget(MDIcon(icon='arrow-down', theme_text_color='Custom', text_color=(1, 1, 1, 1), font_size='32sp', pos_hint={'center_y': 0.5}))
            load_more_box.add_widget(MDLabel(text=f'Charger plus ({remaining})', halign='center', bold=True, theme_text_color='Custom', text_color=(1, 1, 1, 1), font_style='H6', pos_hint={'center_y': 0.5}))
            load_more_card.add_widget(load_more_box)
            self.grid_products.add_widget(load_more_card)

    def _on_load_more_clicked(self):
        children = self.grid_products.children
        if children and (not isinstance(children[0], ProductCard)):
            self.grid_products.remove_widget(children[0])
        self._load_more_products()

    def filter_products_live(self, instance, text):
        filtered = [p for p in self.all_products if text.lower() in p['name'].lower()]
        self.display_products(filtered)

    def open_add_note_dialog(self, product):
        content = MDBoxLayout(orientation='vertical', spacing=20, size_hint_y=None, height=dp(180))
        qty_box = MDBoxLayout(orientation='horizontal', spacing=10, adaptive_height=True, pos_hint={'center_x': 0.5})
        self.qty_field = MDTextField(text='1', hint_text='Quantité', input_filter='float', halign='center', font_size='26sp', size_hint_x=0.4)
        qty_box.add_widget(MDIconButton(icon='minus-box', icon_size='40sp', on_release=lambda x: self.dialog_qty_dec()))
        qty_box.add_widget(self.qty_field)
        qty_box.add_widget(MDIconButton(icon='plus-box', icon_size='40sp', theme_text_color='Custom', text_color=self.theme_cls.primary_color, on_release=lambda x: self.dialog_qty_inc()))
        self.note_field = MDTextField(hint_text='Note (optionnel)', multiline=False)
        content.add_widget(qty_box)
        content.add_widget(self.note_field)
        self.dialog_note = MDDialog(title=f"{product['name']}", type='custom', content_cls=content, buttons=[MDFlatButton(text='ANNULER', on_release=lambda x: self.dialog_note.dismiss()), MDRaisedButton(text='AJOUTER', on_release=lambda x: self.confirm_add(product))])
        self.dialog_note.open()

    def dialog_qty_inc(self):
        try:
            current_qty = float(self.qty_field.text)
            self.qty_field.text = str(int(current_qty + 1))
        except ValueError:
            self.qty_field.text = '1'

    def dialog_qty_dec(self):
        try:
            val = float(self.qty_field.text)
            if val > 1:
                self.qty_field.text = str(int(val - 1))
        except ValueError:
            self.qty_field.text = '1'

    def confirm_add(self, product):
        try:
            qty = DataValidator.validate_quantity(self.qty_field.text)
        except ValueError as e:
            self.notify(str(e), 'error')
            return
        note = DataValidator.sanitize_note(self.note_field.text)
        existing = next((i for i in self.cart if i['id'] == product['id'] and i.get('note') == note), None)
        if existing:
            existing['qty'] += qty
        else:
            try:
                price = float(product['price'])
            except:
                price = 0.0
            self.cart.append({'id': product['id'], 'name': product['name'], 'price': price, 'qty': qty, 'note': note})
        self.dialog_note.dismiss()
        self.update_cart_btn()
        self.notify('Article ajouté au panier avec succès.', 'success')

    def update_cart_btn(self):
        total = sum((float(i['price']) * float(i['qty']) for i in self.cart if i))
        count = sum((float(i['qty']) for i in self.cart if i))
        self.btn_cart.text = f'PANIER ({int(count)}) - {int(total)} DA'

    def show_cart(self, instance=None):
        content = MDBoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None, height=dp(500))
        self.cart_list_container = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(8), padding=dp(5))
        scroll = MDScrollView()
        scroll.add_widget(self.cart_list_container)
        content.add_widget(scroll)
        footer = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(15))
        self.btn_confirm_cart = MDFillRoundFlatButton(text='CONFIRMER', font_size='24sp', size_hint_x=1, height=dp(60), on_release=self.send_order)
        footer.add_widget(self.btn_confirm_cart)
        footer.add_widget(MDFillRoundFlatButton(text='RETOUR', size_hint_x=1, md_bg_color=(0.2, 0.6, 0.9, 1), on_release=lambda x: self.dialog_cart.dismiss()))
        content.add_widget(footer)
        self.dialog_cart = MDDialog(type='custom', content_cls=content, size_hint=(0.9, None))
        self.update_cart_content()
        self.dialog_cart.open()

    def update_cart_content(self):
        if not self.dialog_cart:
            return
        self.cart_list_container.clear_widgets()
        for item in self.cart:
            self.cart_list_container.add_widget(CartItemCard(item, self))
        self.update_cart_totals_live()

    def update_cart_totals_live(self):
        total = sum((float(i['price']) * float(i['qty']) for i in self.cart))
        if hasattr(self, 'btn_confirm_cart'):
            self.btn_confirm_cart.text = f'CONFIRMER - {int(total)} DA'
        self.update_cart_btn()

    def remove_from_cart(self, item):
        if item in self.cart:
            self.cart.remove(item)
            self.update_cart_btn()
            self.update_cart_content()

    def open_edit_note_dialog(self, item):
        content = MDBoxLayout(orientation='vertical', spacing=20, size_hint_y=None, height=dp(100))
        self.edit_note_field = MDTextField(text=item.get('note', ''), hint_text='Modifier note', multiline=False)
        content.add_widget(self.edit_note_field)
        self.dialog_edit_note = MDDialog(title='Modifier Note', type='custom', content_cls=content, buttons=[MDRaisedButton(text='OK', on_release=lambda x: self.save_edited_note(item))])
        self.dialog_edit_note.open()

    def save_edited_note(self, item):
        item['note'] = DataValidator.sanitize_note(self.edit_note_field.text)
        self.dialog_edit_note.dismiss()
        self.update_cart_content()

    def send_order(self, instance):
        if not self.cart:
            self.notify('Votre panier est vide.', 'warning')
            return
        data = {'table_id': self.current_table['id'], 'seat_number': self.current_seat, 'items': self.cart, 'user_name': self.current_user_name, 'timestamp': str(datetime.now())}

        def save_offline(req, error):
            order_key = f'order_{int(datetime.now().timestamp())}_{self.current_seat}'
            self.offline_store.put(order_key, order_data=data)
            self.notify("Mode Hors Ligne : Commande sauvegardée sur l'appareil.", 'warning')
            self.cart = []
            self.update_cart_btn()
            self.go_back()
            if self.dialog_cart:
                self.dialog_cart.dismiss()
            self.silent_refresh(0)
        UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/submit_order', req_body=json.dumps(data), req_headers={'Content-type': 'application/json'}, method='POST', on_success=self.on_sent, on_failure=save_offline, on_error=save_offline, timeout=5)
        if self.dialog_cart:
            self.dialog_cart.dismiss()

    def on_sent(self, req, result):
        self.notify('Commande transmise en cuisine avec succès.', 'success')
        self.cart = []
        self.update_cart_btn()
        self.go_back()

    def process_offline_queue(self):
        keys = list(self.offline_store.keys())
        if not keys:
            if self.dialog_pending:
                self.refresh_pending_dialog_content()
            return
        key = keys[0]
        order_data = self.offline_store.get(key)['order_data']

        def on_sync_success(req, res):
            logging.info(f'Synced order {key}')
            self.offline_store.delete(key)
            if self.dialog_pending:
                self.refresh_pending_dialog_content()
            self.notify(f'Synchronisation effectuée. {len(keys) - 1} commandes restantes.', 'info')
            self.process_offline_queue()

        def on_sync_fail(req, err):
            logging.warning('Sync failed, will try later')
        logging.info(f'Syncing order {key}...')
        UrlRequest(f'http://{self.server_ip}:{DEFAULT_PORT}/api/submit_order', req_body=json.dumps(order_data), req_headers={'Content-type': 'application/json'}, method='POST', on_success=on_sync_success, on_failure=on_sync_fail, on_error=on_sync_fail, timeout=5)

    def on_fail(self, req, error):
        self.notify('Le serveur a rejeté la commande (Erreur 500).', 'error')

    def go_back(self):
        self.screen_manager.current = 'tables'
        self.fetch_tables(manual=True)
        self.start_refresh()

if __name__ == '__main__':
    RestaurantApp().run()
