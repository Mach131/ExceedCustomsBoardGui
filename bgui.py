import json
import luadata
import math
import requests

import PyQt5.QtGui as qg
import PyQt5.QtWidgets as qw
from PyQt5.QtCore import Qt, QRect, QMimeData, QEvent
from PyQt5 import sip

from os import path
import sys
try:
    bundle_dir = sys._MEIPASS
except:
    bundle_dir = path.abspath(path.dirname('./bgui.py'))

BOARD_PARSE_VERSION = 0
BOARD_VERSION_PREFIX = "-- ECBG: Parser Version "

CROSS_BUTTON_PATH = path.join(bundle_dir, './resources/cross-button.png')
OBJECT_TEMPLATE_PATH = path.join(bundle_dir, './resources/object_template.txt')
SCRIPT_BODY_PATH = path.join(bundle_dir, './resources/script_body.txt')

BUTTON_SIZE_FACTOR = 6.5

BGUI_SECTION_PREAMBLE = "-- ====BGUI Section: Preamble===="
BGUI_SECTION_DEFINITIONS = "-- ====BGUI Section: Definitions===="
BGUI_SECTION_COORDINATES = "-- ====BGUI Section: Coordinates===="
BGUI_SECTION_RESIZE = "-- ====BGUI Section: Resize===="
BGUI_SECTION_TOOLTIPS = "-- ====BGUI Section: Tooltips===="
BGUI_SECTION_COLLECTIONS = "-- ====BGUI Section: Collections===="
BGUI_SECTION_JSONS = "-- ====BGUI Section: Json===="
BGUI_SECTION_BODY = "-- ====BGUI Section: Body===="

BGUI_INSERT_NICKNAME = "====BGUI_NICKNAME===="
BGUI_INSERT_IMAGE = "====BGUI_IMAGE===="
BGUI_INSERT_SCRIPT = "====BGUI_SCRIPT===="

PARSEDICT_NICKNAME = "board_nickname"
PARSEDICT_IMAGE_URL = "board_image_url"
PARSEDICT_BUTTON_WIDTH = "default_button_width"
PARSEDICT_CHAR_DEFS = "char_defs"
PARSEDICT_CHAR_COORDS = "char_coords"
PARSEDICT_CHAR_RESIZE = "char_resize"
PARSEDICT_CHAR_TOOLTIPS = "char_tooltip"
PARSEDICT_CHAR_COLLECTIONS = "char_collections"
PARSEDICT_CHAR_JSONS = "char_json"

# https://gis.stackexchange.com/questions/350148/qcombobox-multiple-selection-pyqt5
class CheckableComboBox(qw.QComboBox):
    # Subclass Delegate to increase item height
    class Delegate(qw.QStyledItemDelegate):
        def sizeHint(self, option, index):
            size = super().sizeHint(option, index)
            size.setHeight(20)
            return size

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make the combo editable to set a custom text, but readonly
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        # Make the lineedit the same color as QPushButton
        palette = qw.qApp.palette()
        palette.setBrush(qg.QPalette.Base, palette.button())
        self.lineEdit().setPalette(palette)

        # Use custom delegate
        self.setItemDelegate(CheckableComboBox.Delegate())

        # Update the text when an item is toggled
        self.model().dataChanged.connect(self.updateText)

        # Hide and show popup when clicking the line edit
        self.lineEdit().installEventFilter(self)
        self.closeOnLineEditClick = False

        # Prevent popup from closing when clicking on an item
        self.view().viewport().installEventFilter(self)

    def resizeEvent(self, event):
        # Recompute text to elide as needed
        self.updateText()
        super().resizeEvent(event)

    def eventFilter(self, object, event):
        if object == self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonRelease:
                if self.closeOnLineEditClick:
                    self.hidePopup()
                else:
                    self.showPopup()
                return True
            return False

        if object == self.view().viewport():
            if event.type() == QEvent.Type.MouseButtonRelease:
                index = self.view().indexAt(event.pos())
                item = self.model().item(index.row())

                if item.checkState() == Qt.CheckState.Checked:
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked)
                return True
        return False

    def showPopup(self):
        super().showPopup()
        # When the popup is displayed, a click on the lineedit should close it
        self.closeOnLineEditClick = True

    def hidePopup(self):
        super().hidePopup()
        # Used to prevent immediate reopening when clicking on the lineEdit
        self.startTimer(100)
        # Refresh the display text when closing
        self.updateText()

    def timerEvent(self, event):
        # After timeout, kill timer, and reenable click on line edit
        self.killTimer(event.timerId())
        self.closeOnLineEditClick = False

    def updateText(self):
        texts = []
        for i in range(self.model().rowCount()):
            if self.model().item(i).checkState() == Qt.Checked:
                texts.append(self.model().item(i).text())
        text = ", ".join(texts)

        # Compute elided text (with "...")
        metrics = qg.QFontMetrics(self.lineEdit().font())
        elidedText = metrics.elidedText(text, Qt.ElideRight, self.lineEdit().width())
        self.lineEdit().setText(elidedText)

    def addItem(self, text, data=None):
        item = qg.QStandardItem()
        item.setText(text)
        if data is None:
            item.setData(text)
        else:
            item.setData(data)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        self.model().appendRow(item)

    def addItems(self, texts, datalist=None):
        for i, text in enumerate(texts):
            try:
                data = datalist[i] if datalist is not None else None
            except (TypeError, IndexError):
                data = None
            self.addItem(text, data)

    def currentTextList(self):
        # Return the list of selected items test
        res = []
        for i in range(self.model().rowCount()):
            if self.model().item(i).checkState() == Qt.Checked:
                res.append(self.model().item(i).text())
        return res

    def currentData(self):
        # Return the list of selected items data
        res = []
        for i in range(self.model().rowCount()):
            if self.model().item(i).checkState() == Qt.Checked:
                res.append(self.model().item(i).data())
        return res
    

class ImageLabel(qw.QLabel):
    def __init__(self, file_open_callback):
        super().__init__()
        self.file_open_callback = file_open_callback
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText('\n\nDrop Board Image/JSON Here or Click To Browse\n\n')
        self.setToolTip('Click to Browse for Board Image/JSON')
        self.setStyleSheet(
            "QLabel {" + \
            "   border: 4px dashed #aaa;" + \
            "}"
        )
    
    def setPixmap(self, *args, **kwargs):
        super().setPixmap(*args, **kwargs)
        # self.setStyleSheet(
        #     "QLabel {" + \
        #     "   border: none;" + \
        #     "}"
        # )

    def mouseReleaseEvent(self, ev):
        self.file_open_callback()
        return super().mouseReleaseEvent(ev)

class BoardImageUpload(qw.QWidget):
    def __init__(self, board_image_update_callback, board_json_upload_callback, clear_callback):
        super().__init__()
        self.board_image_update_callback = board_image_update_callback
        self.board_json_upload_callback = board_json_upload_callback
        self.clear_callback = clear_callback

        self.image = ImageLabel(self.open_image)
        self.pixmap = None
        self.image_loaded = False
        # btn = qw.QPushButton('Browse')
        # btn.clicked.connect(self.open_image)
        self.dimensionLabel = qw.QLabel("")

        grid = qw.QGridLayout(self)
        grid.addWidget(self.image, 0, 0)
        grid.addWidget(self.dimensionLabel, 1, 0, Qt.AlignmentFlag.AlignHCenter)
        # grid.addWidget(btn, 2, 0, Qt.AlignmentFlag.AlignHCenter)
        self.setAcceptDrops(True)
        self.resize(300, 200)

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage():
            event.accept()
            return
        elif event.mimeData().hasUrls():
            filename = event.mimeData().urls()[0].toLocalFile()
            if filename.endswith("png") or filename.endswith("jpg") or filename.endswith("jpeg") or filename.endswith("json"):
                event.accept()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasImage():
            event.accept()
            return
        elif event.mimeData().hasUrls():
            filename = event.mimeData().urls()[0].toLocalFile()
            if filename.endswith("png") or filename.endswith("jpg") or filename.endswith("jpeg") or filename.endswith("json"):
                event.accept()
                return
        event.ignore()
            
    def dropEvent(self, event):
        if event.mimeData().hasImage():
            event.setDropAction(Qt.DropAction.CopyAction)
            filename = event.mimeData().urls()[0].toLocalFile()
            event.accept()
            self.open_image(filename)
            return
        elif event.mimeData().hasUrls():
            filename = event.mimeData().urls()[0].toLocalFile()
            if filename.endswith("png") or filename.endswith("jpg") or filename.endswith("jpeg"):
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                self.open_image(filename)
                return
            elif filename.endswith("json"):
                event.accept()
                self.parse_board_json(filename)
                return
        event.ignore()

    def open_image(self, filename=None):
        if not filename:
            filename, _ = qw.QFileDialog.getOpenFileName(self, 'Select Board Image', '.', 'Images (*.png *.jpg);;JSON files (*.json)')
            if not filename:
                return
        if filename.endswith("json"):
            self.parse_board_json(filename)
        else:
            self.pixmap = qg.QPixmap(filename)
            self.finish_open_image()

    def open_image_from_data(self, image_data):
        self.pixmap = image_data
        self.finish_open_image()
        
    def finish_open_image(self):
        self.image.setPixmap(self.pixmap.scaledToHeight(self.height()))
        self.dimensionLabel.setText(f"Dimensions: {self.pixmap.width()}x{self.pixmap.height()}")
        self.image_loaded = True
        self.board_image_update_callback()

    def clear(self):
        self.image.clear()
        self.pixmap = None
        self.image_loaded = False
        self.dimensionLabel.setText("")

    def parse_board_json(self, filename):
        if self.pixmap is not None:
            self.clear_callback()
        
        with open(filename, 'r', encoding='utf-8') as f:
            board_json = json.load(f)["ObjectStates"][0]
            board_nickname = board_json["Nickname"]
            board_image_url = board_json["CustomImage"]["ImageURL"]

            board_script : str = board_json["LuaScript"].split(BGUI_SECTION_PREAMBLE)[1]
            board_script_preamble, board_script = board_script.split(BGUI_SECTION_DEFINITIONS)
            board_script_definitions, board_script = board_script.split(BGUI_SECTION_COORDINATES)
            board_script_coordinates, board_script = board_script.split(BGUI_SECTION_RESIZE)
            board_script_resize, board_script = board_script.split(BGUI_SECTION_TOOLTIPS)
            board_script_tooltips, board_script = board_script.split(BGUI_SECTION_COLLECTIONS)
            board_script_collections, board_script = board_script.split(BGUI_SECTION_JSONS)
            board_script_jsons, board_script = board_script.split(BGUI_SECTION_BODY)

            parse_version = 0
            
            parse_dict = {PARSEDICT_NICKNAME: board_nickname, PARSEDICT_IMAGE_URL: board_image_url}
            for line in board_script_preamble.strip().splitlines():
                ls = line.strip()
                if ls.startswith(BOARD_VERSION_PREFIX):
                    value = int(ls[len(BOARD_VERSION_PREFIX):].strip())
                    parse_version = value
                if ls.startswith("button_width"):
                    uncommented_value = ls.split("--")[0]
                    value = int(uncommented_value.split("=")[1].strip())
                    parse_dict[PARSEDICT_BUTTON_WIDTH] = value

            char_defs = []
            for line in board_script_definitions.strip().splitlines():
                ls = line.strip().split('=', 1)
                if len(ls) == 2:
                    char_defs.append(ls[0].strip())
            parse_dict[PARSEDICT_CHAR_DEFS] = char_defs

            char_coord_dict = {}
            for line in board_script_coordinates.strip().splitlines()[1:]:
                if line.startswith('--'):
                    continue
                ls = line.strip().split('=', 1)
                if ls[0].strip() == 'character_coordinate_map':
                    continue
                if len(ls) == 2:
                    char = ls[0].strip()
                    coords = ls[1].replace('{', '').replace('}', '').split(',')
                    char_coord_dict[char] = (int(coords[0].strip()), int(coords[1].strip()))
            parse_dict[PARSEDICT_CHAR_COORDS] = char_coord_dict

            char_resize_dict = {}
            for line in board_script_resize.strip().splitlines()[1:]:
                if line.startswith('--'):
                    continue
                ls = line.strip().split('=', 1)
                if ls[0].strip() == 'button_resize_map':
                    continue
                if len(ls) == 2:
                    char = ls[0].strip()
                    coords = ls[1].replace('{', '').replace('}', '').split(',')
                    char_resize_dict[char] = (float(coords[0].strip()), float(coords[1].strip()))
            parse_dict[PARSEDICT_CHAR_RESIZE] = char_resize_dict

            char_tooltip_dict = {}
            for line in board_script_tooltips.strip().splitlines()[1:]:
                if line.startswith('--'):
                    continue
                ls = line.strip().split('=', 1)
                if ls[0].strip() == 'character_tooltip_map':
                    continue
                if len(ls) == 2:
                    char = ls[0].strip()
                    tooltip = ls[1].strip(' ,')[1:-1]
                    char_tooltip_dict[char] = tooltip
            parse_dict[PARSEDICT_CHAR_TOOLTIPS] = char_tooltip_dict

            char_collection_dict = {}
            current_collection_char = ""
            current_collection_string = ""
            scanning_group = False
            for line in board_script_collections.strip().splitlines()[1:]:
                if scanning_group:
                    new_line = line.strip()
                    if new_line.startswith("characters =") or new_line.startswith("sequence ="):
                        for char in parse_dict[PARSEDICT_CHAR_DEFS]:
                            new_line = new_line.replace(char, f'"{char}"')
                    elif new_line == "color_string = [[{":
                        new_line = "color_string = {"
                    elif new_line.startswith("}]]"):
                        new_line = "}" + (',' if new_line[-1] == ',' else '')
                    current_collection_string += new_line

                if line.startswith('\t') and not line.startswith('\t\t'):
                    if not scanning_group:
                        ls = line.strip().split('=', 1)
                        if len(ls) == 2:
                            scanning_group = True
                            current_collection_char = ls[0].strip()
                            current_collection_string = ls[1].strip()
                    else:
                        if current_collection_string[-1] == ',':
                            current_collection_string = current_collection_string[:-1]
                        for color_prefix in ('"r": ', '"g": ', '"b": '):
                            current_collection_string = current_collection_string.replace(color_prefix, f'{color_prefix[1]} = ')

                        current_collection_json = luadata.unserialize(current_collection_string)

                        password_set = {}
                        char_collection_dict[current_collection_char] = (
                            current_collection_json['characters'],
                            (current_collection_json['color_string']['r'], current_collection_json['color_string']['g'], current_collection_json['color_string']['b']),
                            password_set,
                            (current_collection_json.get('left_click_spawn_random', False), current_collection_json.get('right_click_spawn_random', True)),
                            current_collection_json.get('random_weights', {})
                        )
                        for password_char in current_collection_json.get('passwords', []):
                            password_data = current_collection_json['passwords'][password_char]
                            password_set[password_char] = (password_data['sequence'], password_data['message'])


                        scanning_group = False

            parse_dict[PARSEDICT_CHAR_COLLECTIONS] = char_collection_dict

            char_json_dict = {}
            for line in board_script_jsons.strip().splitlines()[1:]:
                if line.startswith('--'):
                    continue
                ls = line.strip().split('=', 1)
                if ls[0].strip() == 'character_tooltip_map':
                    continue
                if len(ls) == 2:
                    char = ls[0].strip()
                    json_core = ls[1].strip(' ,[]')[1:-1]
                    json_dummy = json.loads(f"{{{json_core}}}")
                    full_json_dummy = {"SampleText": "Dummy Outer JSON", "ObjectStates": [json_dummy]}
                    char_json_dict[char] = json.dumps(full_json_dummy)
            parse_dict[PARSEDICT_CHAR_JSONS] = char_json_dict

            self.board_json_upload_callback(parse_dict)


class CharJsonUpload(qw.QWidget):
    def __init__(self, text_changed_callback):
        super().__init__()
        self.setAcceptDrops(True)

        layout = qw.QHBoxLayout()

        layout_json_prefix = qw.QVBoxLayout()
        json_load_btn = qw.QPushButton('Browse')
        json_load_btn.clicked.connect(self.open_json_file)
        main_label = qw.QLabel('Full character JSON: ')
        layout_json_prefix.addWidget(main_label)
        layout_json_prefix.addWidget(json_load_btn)

        layout.addLayout(layout_json_prefix)
        self.char_json_entry = qw.QTextEdit()
        self.char_json_entry.setAcceptDrops(False)
        self.char_json_entry.setPlaceholderText("(You can also drag and drop jsons into this box hopefully)")
        self.char_json_entry.textChanged.connect(text_changed_callback)
        layout.addWidget(self.char_json_entry)

        self.setLayout(layout)
        main_label.setToolTip("The full JSON for the character (don't worry about doing any reformatting, like you would if you've messed with the script directly before).\n" + \
                        "You should be able to drag and drop a JSON file into the text box, or you can press Browse to add one normally.")

    def get_json_text(self):
        return self.char_json_entry.toPlainText()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            filename = event.mimeData().urls()[0].toLocalFile()
            if filename.endswith("json"):
                event.accept()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            filename = event.mimeData().urls()[0].toLocalFile()
            if filename.endswith("json"):
                event.accept()
                return
        event.ignore()
            
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            filename = event.mimeData().urls()[0].toLocalFile()
            if filename.endswith("json"):
                event.setDropAction(Qt.DropAction.CopyAction)
                filename = event.mimeData().urls()[0].toLocalFile()
                event.accept()
                self.open_json_file(filename)
                return
        event.ignore()

    def open_json_file(self, filename=None):
        if not filename:
            filename, _ = qw.QFileDialog.getOpenFileName(self, 'Select Character JSON', '.', 'JSON (*.json)')
            if not filename:
                return
        with open(filename, 'r') as jf:
            self.char_json_entry.setPlainText(jf.read())

class BoardButtonField(qw.QWidget):
    def __init__(self, allow_hide : bool, id : str, board_image : qg.QPixmap, button_size : tuple[int, int], *setup_params):
        super().__init__()

        self.id = id
        self.hide_on_board = False
        self.char_label = ""
        self.char_json = ""
        self.button_size = button_size
        self.button_x = 0
        self.button_y = 0

        self.board_image = board_image
        self.board_image_size = (0, 0)

        layout = qw.QHBoxLayout()
        layout.setSpacing(50)

        self.preview_image = qw.QLabel()
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.preview_image.setToolTip("Preview of what part of the image the button will include.\n" + \
                                      "(You can drag this whole block above/below other characters/groups to reorder, if needed.)")
        layout.addWidget(self.preview_image)

        layout_fields = qw.QVBoxLayout()
        layout_fields_top = qw.QHBoxLayout()
        layout_fields_top.setSpacing(10)

        id_label = qw.QLabel('ID: ')
        layout_fields_top.addWidget(id_label)
        id_label.setToolTip("The ID for this character/group. Should be unique from every other ID, and only use alphanumeric characters and/or underscores.")
        self.id_entry = qw.QLineEdit()
        self.id_entry.setText(id)
        self.id_entry.textChanged.connect(self.set_id)
        layout_fields_top.addWidget(self.id_entry)

        if allow_hide:
            hide_label = qw.QLabel('Hide on Board?')
            layout_fields_top.addWidget(hide_label)
            hide_label.setToolTip("Check this if the character shouldn't have a button on the board. Useful for password-only characters.")
            self.hide_on_board_checkbox = qw.QCheckBox()
            self.hide_on_board_checkbox.setChecked(False)
            self.hide_on_board_checkbox.clicked.connect(self.set_hide_on_board)
            layout_fields_top.addWidget(self.hide_on_board_checkbox)

        label_label = qw.QLabel('Button Label: ')
        layout_fields_top.addWidget(label_label)
        label_label.setToolTip("The tooltip that will appear when hovering over the button in TTS.")
        self.char_label_entry = qw.QLineEdit()
        self.char_label_entry.textChanged.connect(self.set_char_label)
        layout_fields_top.addWidget(self.char_label_entry)

        x_label = qw.QLabel('x: ')
        layout_fields_top.addWidget(x_label)
        x_label.setToolTip("The horizontal position of the center of the button, in pixels.")
        self.x_spinner = qw.QSpinBox()
        self.x_spinner.setMinimum(0)
        self.x_spinner.setMaximum(1000000)
        # self.x_spinner.setSingleStep(self.board_image_size[0] // 30)
        self.x_spinner.valueChanged.connect(self.update_button_x)
        layout_fields_top.addWidget(self.x_spinner)

        y_label = qw.QLabel('y: ')
        layout_fields_top.addWidget(y_label)
        y_label.setToolTip("The vertical position of the center of the button, in pixels.")
        self.y_spinner = qw.QSpinBox()
        self.y_spinner.setMinimum(0)
        self.y_spinner.setMaximum(1000000)
        # self.y_spinner.setSingleStep(self.board_image_size[1] // 30)
        self.y_spinner.valueChanged.connect(self.update_button_y)
        layout_fields_top.addWidget(self.y_spinner)

        w_label = qw.QLabel('w: ')
        layout_fields_top.addWidget(w_label)
        w_label.setToolTip("The horizontal size (width) of the button, in pixels.")
        self.w_spinner = qw.QSpinBox()
        self.w_spinner.setMinimum(0)
        self.w_spinner.setMaximum(1000000)
        # self.w_spinner.setSingleStep(self.board_image_size[0] // 30)
        self.w_spinner.setValue(self.button_size[0])
        self.w_spinner.valueChanged.connect(self.update_button_w)
        layout_fields_top.addWidget(self.w_spinner)

        h_label = qw.QLabel('h: ')
        layout_fields_top.addWidget(h_label)
        h_label.setToolTip("The vertical size (height) of the button, in pixels.")
        self.h_spinner = qw.QSpinBox()
        self.h_spinner.setMinimum(0)
        self.h_spinner.setMaximum(1000000)
        # self.h_spinner.setSingleStep(self.board_image_size[1] // 30)
        self.h_spinner.setValue(self.button_size[1])
        self.h_spinner.valueChanged.connect(self.update_button_h)
        layout_fields_top.addWidget(self.h_spinner)
        
        layout_fields_top.addStretch()
        layout_fields.addLayout(layout_fields_top)

        self.setup_additional_layout_fields(layout_fields, *setup_params)

        layout.addLayout(layout_fields)
        self.update_board_image(board_image)
        self.setLayout(layout)
        self.setAcceptDrops(True)

    def setup_additional_layout_fields(self, layout_fields):
        pass

    def update_board_image(self, board_image : qg.QPixmap, *setup_params):
        if board_image is None:
            return
        
        self.board_image = board_image
        self.board_image_size = (board_image.width(), board_image.height())
        self.w_spinner.setMaximum(self.board_image_size[0])
        self.w_spinner.setSingleStep(math.ceil(self.board_image_size[0] / 30))
        self.h_spinner.setMaximum(self.board_image_size[1])
        self.h_spinner.setSingleStep(math.ceil(self.board_image_size[1] / 30))

        if self.button_size[0] > self.board_image_size[0]:
            self.button_size = (self.board_image_size[0], self.button_size[1])
            self.w_spinner.setValue(self.button_size[0])
        if self.button_size[1] > self.board_image_size[1]:
            self.button_size = (self.button_size[0], self.board_image_size[1])
            self.h_spinner.setValue(self.button_size[1])

        board_extents = (max(self.board_image_size[0] - (self.button_size[0] // 2), 0), max(self.board_image_size[1] - (self.button_size[1] // 2), 0))
        self.x_spinner.setMinimum(self.button_size[0] // 2)
        self.x_spinner.setMaximum(max(self.button_size[0] // 2, board_extents[0]))
        self.x_spinner.setSingleStep(math.ceil(self.board_image_size[0] / 30))
        self.y_spinner.setMinimum(self.button_size[1] // 2)
        self.y_spinner.setMaximum(max(self.button_size[1] // 2, board_extents[1]))
        self.y_spinner.setSingleStep(math.ceil(self.board_image_size[1] / 30))

        if self.button_x > board_extents[0]:
            self.button_x = board_extents[0]
            self.x_spinner.setValue(self.button_x)
        if self.button_y > board_extents[1]:
            self.button_y = board_extents[1]
            self.y_spinner.setValue(self.button_y)
            
        self.update_preview_image()

    def update_button_x(self, new_x):
        self.button_x = new_x
        self.update_preview_image()

    def update_button_y(self, new_y):
        self.button_y = new_y
        self.update_preview_image()

    def update_button_w(self, new_w):
        self.button_size = (new_w, self.button_size[1])
        board_extent_x = max(self.board_image_size[0] - (new_w // 2), 0)
        self.x_spinner.setMinimum(new_w // 2)
        self.x_spinner.setMaximum(max(new_w // 2, board_extent_x))
        self.update_preview_image()

    def update_button_h(self, new_h):
        self.button_size = (self.button_size[0], new_h)
        board_extent_y = max(self.board_image_size[1] - (new_h // 2), 0)
        self.y_spinner.setMinimum(new_h // 2)
        self.y_spinner.setMaximum(max(new_h // 2, board_extent_y))
        self.update_preview_image()

    def update_preview_image(self):
        sub_image = qg.QPixmap(*self.button_size)
        qp = qg.QPainter(sub_image)
        top_corner = (self.button_x - (self.button_size[0] // 2), self.button_y - (self.button_size[1] // 2))
        painter_rect = QRect(top_corner[0], top_corner[1], self.button_size[0], self.button_size[1])
        qp.drawPixmap(sub_image.rect(), self.board_image, painter_rect)
        qp.end()
        self.preview_image.setPixmap(sub_image.scaledToWidth(150))

    def set_id(self):
        self.id = self.id_entry.text()

    def set_char_label(self):
        self.char_label = self.char_label_entry.text()

    def set_hide_on_board(self, hidden):
        self.hide_on_board = hidden
        self.preview_image.setVisible(not hidden)
        self.char_label_entry.setEnabled(not hidden)
        self.x_spinner.setEnabled(not hidden)
        self.y_spinner.setEnabled(not hidden)

    def mouseMoveEvent(self, a0: qg.QMouseEvent | None) -> None:
        if a0 is None:
            return
        
        if a0.buttons() == Qt.MouseButton.LeftButton:
            drag = qg.QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)

            pixmap = qg.QPixmap(self.size())
            self.render(pixmap)
            drag.setPixmap(pixmap)

            drag.exec()


class CharacterField(BoardButtonField):
    def __init__(self, char_id : str, board_image : qg.QPixmap, button_size : tuple[int, int]):
        super().__init__(True, char_id, board_image, button_size)

    def setup_additional_layout_fields(self, layout_fields, *setup_params):
        layout_fields_bottom = qw.QHBoxLayout()

        self.char_json_entry = CharJsonUpload(self.set_char_json)
        layout_fields_bottom.addWidget(self.char_json_entry)
    
        layout_fields.addLayout(layout_fields_bottom)

    def set_char_json(self):
        self.char_json = self.char_json_entry.get_json_text()

    def get_parsed_json(self):
        json_form = json.loads(self.char_json)
        str_form = json.dumps(json_form["ObjectStates"][0])
        return str_form.replace('\n', '').replace('\r', '')

class GroupField(BoardButtonField):
    def __init__(self, group_id : str, board_image : qg.QPixmap, button_size : tuple[int, int],
                 char_widgets : list[CharacterField]):
        super().__init__(False, group_id, board_image, button_size, char_widgets)

    def setup_additional_layout_fields(self, layout_fields, *setup_params):
        char_widgets : list[CharacterField] = setup_params[0]
        self.random_char_weights = {}

        layout_fields.setSpacing(10)

        layout_fields_bottom = qw.QHBoxLayout()

        layout_fields_bottom.addStretch()

        layout_fields_main = qw.QVBoxLayout()
        layout_fields_main.setSpacing(2)

        layout_fields_main_characters = qw.QHBoxLayout()
        include_label = qw.QLabel('Included Characters: ')
        layout_fields_main_characters.addWidget(include_label)
        include_label.setToolTip("The list of characters included in this group's pool of options.")
        self.member_selection = CheckableComboBox()
        self.member_selection.setMinimumWidth(int(self.width() * 0.5))
        self.member_selection.currentTextChanged.connect(self.rescan_weights)
        self.rename_signals = []
        for char in char_widgets:
            self.add_char(char)
        layout_fields_main_characters.addWidget(self.member_selection)
        layout_fields_main.addLayout(layout_fields_main_characters)

        layout_fields_main_clicks = qw.QHBoxLayout()
        layout_fields_main_clicks.addStretch()
        self.left_click_spawns_random = False
        self.right_click_spawns_random = True

        # Left click
        self.left_click_button_group = qw.QButtonGroup()
        layout_left_click_button_group = qw.QVBoxLayout()
        layout_left_click_button_group.setSpacing(5)

        left_label = qw.QLabel("Left Click Function:")
        layout_left_click_button_group.addWidget(left_label)
        left_label.setToolTip("What to spawn when left-clicking this group button.")
        self.left_click_random_button = qw.QRadioButton("Spawn Random Character")
        self.left_click_random_button.setToolTip("When left-clicking, spawn a random character from the included characters.")
        self.left_click_random_button.clicked.connect(lambda x: self.left_click_function_toggled(True))
        self.left_click_button_group.addButton(self.left_click_random_button)
        layout_left_click_button_group.addWidget(self.left_click_random_button)

        self.left_click_group_button = qw.QRadioButton("Spawn Full Group Bag")
        self.left_click_group_button.setToolTip("When left-clicking, spawn a bag containing all of the included characters.")
        self.left_click_group_button.click()
        self.left_click_group_button.clicked.connect(lambda x: self.left_click_function_toggled(False))
        self.left_click_button_group.addButton(self.left_click_group_button)
        layout_left_click_button_group.addWidget(self.left_click_group_button)

        layout_fields_main_clicks.addLayout(layout_left_click_button_group)

        # Right click
        self.right_click_button_group = qw.QButtonGroup()
        layout_right_click_button_group = qw.QVBoxLayout()
        layout_right_click_button_group.setSpacing(5)

        right_label = qw.QLabel("Right Click Function:")
        layout_right_click_button_group.addWidget(right_label)
        right_label.setToolTip("What to spawn when right-clicking this group button.")
        self.right_click_random_button = qw.QRadioButton("Spawn Random Character")
        self.right_click_random_button.setToolTip("When right-clicking, spawn a random character from the included characters.")
        self.right_click_random_button.click()
        self.right_click_random_button.clicked.connect(lambda x: self.right_click_function_toggled(True))
        self.right_click_button_group.addButton(self.right_click_random_button)
        layout_right_click_button_group.addWidget(self.right_click_random_button)

        self.right_click_group_button = qw.QRadioButton("Spawn Full Group Bag")
        self.right_click_group_button.setToolTip("When right-clicking, spawn a bag containing all of the included characters.")
        self.right_click_group_button.clicked.connect(lambda x: self.right_click_function_toggled(False))
        self.right_click_button_group.addButton(self.right_click_group_button)
        layout_right_click_button_group.addWidget(self.right_click_group_button)

        layout_fields_main_clicks.addLayout(layout_right_click_button_group)

        # done with click toggles

        layout_fields_main_clicks.addStretch()
        self.weights_window = None
        weights_button = qw.QPushButton("Edit Random\nWeights")
        weights_button.setToolTip("Adjust the relative chances for characters to show up when spawning a random character.")
        weights_button.clicked.connect(self.open_weights_window)
        layout_fields_main_clicks.addWidget(weights_button)

        layout_fields_main_clicks.addStretch()
        layout_fields_main.addLayout(layout_fields_main_clicks)
        layout_fields_bottom.addLayout(layout_fields_main)

        layout_fields_bottom.addStretch()

        self.bag_color = qg.QColor()
        color_select_button = qw.QPushButton('Change Bag Color')
        color_select_button.setToolTip("Adjust the color of the bag spawned when creating a full group bag.")
        color_select_button.clicked.connect(self.select_color)
        layout_fields_bottom.addWidget(color_select_button)

        self.preview_field = qw.QGraphicsView()
        self.preview_field.setToolTip("A preview of the selected full group bag color.")
        self.preview_field.resize(32, 32)
        self.preview_field.setStyleSheet('background:transparent')
        scene = qw.QGraphicsScene()
        self.preview_field.setScene(scene)
        self.preview_square = qw.QGraphicsRectItem(0, 0, 64, 64)
        self.preview_square.setPen(self.bag_color)
        self.preview_square.setBrush(qg.QBrush((self.bag_color)))
        scene.addItem(self.preview_square)
        layout_fields_bottom.addWidget(self.preview_field)

        layout_fields_bottom.addStretch()

        self.passwords = {}
        self.password_window = None
        password_button = qw.QPushButton("Edit Password\nCharacters")
        password_button.setToolTip("Edit sequences of characters that can be used to spawn other (secret) characters with this group button.")
        password_button.clicked.connect(self.open_password_window)
        layout_fields_bottom.addWidget(password_button)

        layout_fields_bottom.addStretch()
    
        layout_fields.addLayout(layout_fields_bottom)
        # layout_fields.addStretch()

    def disconnect_rename_signals(self):
        for rename_signal, response_func in self.rename_signals:
            rename_signal.disconnect(response_func)

    def add_char(self, char_widget : CharacterField):
        next_idx = self.member_selection.count()
        self.member_selection.addItem(char_widget.id)
        self.member_selection.setItemData(next_idx, char_widget)

        new_rename_signal = (lambda c: (lambda t: self.update_char_id(c, t)))(char_widget)
        char_widget.id_entry.textChanged.connect(new_rename_signal)
        self.rename_signals.append((char_widget.id_entry.textChanged, new_rename_signal))

    def find_char(self, char_widget : CharacterField):
        for i in range(self.member_selection.count()):
            check_data = self.member_selection.itemData(i)
            if check_data == char_widget:
                return i
        return -1

    def delete_char(self, char_widget : CharacterField):
        char_idx = self.find_char(char_widget)
        self.member_selection.removeItem(char_idx)
        self.member_selection.updateText()
        self.random_char_weights.pop(char_widget.char_label)
        
    def update_char_id(self, char_widget : CharacterField, new_id : str):
        char_idx = self.find_char(char_widget)
        old_id = self.member_selection.itemText(char_idx)
        self.member_selection.setItemText(char_idx, new_id)

        if old_id in self.random_char_weights:
            old_weight = self.random_char_weights.pop(old_id)
            self.random_char_weights[new_id] = old_weight
        self.member_selection.updateText()

    def select_color(self, _=None, color=None):
        if color is None:
            color = qw.QColorDialog(self).getColor()
        if color.isValid:
            self.bag_color = color
            self.preview_square.setPen(self.bag_color)
            self.preview_square.setBrush(qg.QBrush((self.bag_color)))

    def open_password_window(self):
        if self.password_window is not None and not self.password_window.isVisible():
            self.password_window.deleteLater()
            self.password_window = None

        if self.password_window is None:
            self.password_window = GroupPasswordEditor(self)
        self.password_window.show()

    def open_weights_window(self):
        if self.weights_window is not None and not self.weights_window.isVisible():
            self.weights_window.deleteLater()
            self.weights_window = None

        if self.weights_window is None:
            self.weights_window = GroupRandomWeightEditor(self)
        self.weights_window.show()

    def left_click_function_toggled(self, state):
        self.left_click_spawns_random = state

    def right_click_function_toggled(self, state):
        self.right_click_spawns_random = state

    def rescan_weights(self):
        for char_idx in range(self.member_selection.count()):
            char = self.member_selection.itemText(char_idx)
            if char in self.random_char_weights and self.member_selection.model().item(char_idx).checkState() == Qt.Unchecked:
                self.random_char_weights.pop(char)

class GroupRandomWeightEditor(qw.QDialog):
    def __init__(self, group_field : GroupField, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle(f"Random Weights for {group_field.char_label}")
        self.group_field = group_field
        layout = qw.QVBoxLayout()
        weight_label = qw.QLabel(f"Editing Random Character Weights")
        layout.addWidget(weight_label)

        self.layout_seq_list = qw.QVBoxLayout()
        for char_idx in range(self.group_field.member_selection.count()):
            if self.group_field.member_selection.model().item(char_idx).checkState() == Qt.Checked:
                char = self.group_field.member_selection.itemText(char_idx)
                self.add_seq_char_layout(char)
        layout.addLayout(self.layout_seq_list)

        self.setLayout(layout)
    
    def add_seq_char_layout(self, seq_char):
        layout_char = qw.QHBoxLayout()

        char_label = qw.QLabel("    " + seq_char)
        layout_char.addWidget(char_label)
        char_label.setToolTip("Change the number next to a character to adjust their chances of spawning with this random button (default is 1.0).\n" + \
                                "For instance, if you have one character with a weight of 3 and another with a weight of 1, the first one will spawn 3 times as often.")
        weight_spinner = qw.QDoubleSpinBox()
        weight_spinner.setMinimum(0)
        weight_spinner.setMaximum(2147483647)
        weight_spinner.setValue(self.group_field.random_char_weights.get(seq_char, 1))
        weight_spinner.valueChanged.connect(lambda v: self.update_weight(seq_char, v))
        layout_char.addWidget(weight_spinner)

        self.layout_seq_list.addLayout(layout_char)

    def update_weight(self, char, new_value):
        self.group_field.random_char_weights[char] = new_value


class GroupPasswordEditor(qw.QDialog):
    def __init__(self, group_field : GroupField, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle(f"Passwords for {group_field.char_label}")
        self.group_field = group_field
        self.password_char_window = None
        self.char_password_map = {}

        layout = qw.QVBoxLayout()

        self.layout_char_list = qw.QVBoxLayout()

        for password_char in self.group_field.passwords:
            self.add_char_layout(password_char)
        layout.addLayout(self.layout_char_list)

        layout_add_char = qw.QHBoxLayout()
        self.add_character_dropdown = qw.QComboBox()
        self.add_character_dropdown.clear()
        for i in range(self.group_field.member_selection.count()):
            self.add_character_dropdown.addItem(self.group_field.member_selection.itemText(i))
        layout_add_char.addWidget(self.add_character_dropdown)
        add_character_button = qw.QPushButton("Add Hidden Character")
        add_character_button.setToolTip("Add a new character that can be spawned with a 'password' sequence.")
        add_character_button.pressed.connect(self.add_password_character)
        layout_add_char.addWidget(add_character_button)

        layout.addLayout(layout_add_char)
        self.setLayout(layout)

    def add_char_layout(self, password_char):
        layout_char = qw.QHBoxLayout()
        layout_char.addWidget(qw.QLabel(password_char))
        edit_button = qw.QPushButton("Edit Sequence")
        edit_button.setToolTip("Edit this character's password sequence.")
        edit_button.clicked.connect(lambda x: self.open_password_character(password_char))
        layout_char.addWidget(edit_button)
        delete_button = qw.QPushButton("Remove")
        delete_button.setToolTip("Remove this character's password sequence (they will no longer be spawnable through a password).")
        delete_button.clicked.connect(lambda x: self.remove_password_character(password_char))
        layout_char.addWidget(delete_button)
        self.layout_char_list.addLayout(layout_char)
        self.char_password_map[password_char] = layout_char

    def add_password_character(self):
        new_char = self.add_character_dropdown.currentText()
        if new_char not in self.group_field.passwords:
            self.group_field.passwords[new_char] = [[], ""]
            self.add_char_layout(new_char)
        self.open_password_character(new_char)

    def remove_password_character(self, char):
        target_layout = self.char_password_map[char]
        self.layout_char_list.removeItem(target_layout)
        self.group_field.passwords.pop(char)
        self.char_password_map.pop(char)
        deleteLayout(target_layout)

    def open_password_character(self, char):
        if self.password_char_window is None:
            self.password_char_window = GroupPasswordCharEditor(self.group_field)
        self.password_char_window.load_char(char)
        self.password_char_window.show()

class GroupPasswordCharEditor(qw.QDialog):
    def __init__(self, group_field : GroupField, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle("Password Sequence")
        self.group_field = group_field
        
    def load_char(self, char_label):
        deleteLayout(self.layout())

        self.char_label = char_label
        layout = qw.QVBoxLayout()

        self.setWindowTitle(f"Password Sequence: {self.char_label}")
        title_label = qw.QLabel(f"Editing Password Sequence for: {self.char_label}")
        layout.addWidget(title_label)
        title_label.setToolTip("Define a password sequence by adding characters; if someone presses their buttons in order (from top to bottom)\n" + \
                               "and then presses on this group button, the secret character will spawn (and the message will be shown to the player who spawned them).")

        self.layout_seq_list = qw.QVBoxLayout()
        self.password_data = self.group_field.passwords[char_label]
        for char in self.password_data[0]:
            self.add_seq_char_layout(char)
        layout.addLayout(self.layout_seq_list)

        layout_add_char = qw.QHBoxLayout()
        self.add_character_dropdown = qw.QComboBox()
        self.add_character_dropdown.clear()
        for i in range(self.group_field.member_selection.count()):
            self.add_character_dropdown.addItem(self.group_field.member_selection.itemText(i))
        layout_add_char.addWidget(self.add_character_dropdown)
        add_character_button = qw.QPushButton("Add Sequence Character")
        add_character_button.setToolTip("Add a character to the end of the password sequence.")
        add_character_button.pressed.connect(self.add_sequence_character)
        layout_add_char.addWidget(add_character_button)
        layout.addLayout(layout_add_char)

        layout_spawn_message = qw.QHBoxLayout()
        spawn_label = qw.QLabel("Spawn Message: ")
        layout_spawn_message.addWidget(spawn_label)
        spawn_label.setToolTip("A message to be shown to the player who spawns the secret character through this group button.\n" + \
                               "(Note that if the character can also appear as a normal random option, this message will also show if they get rolled.)")
        self.spawn_message_box = qw.QLineEdit(self.group_field.passwords[self.char_label][1])
        self.spawn_message_box.textChanged.connect(self.update_spawn_message)
        layout_spawn_message.addWidget(self.spawn_message_box)
        layout.addLayout(layout_spawn_message)

        self.setLayout(layout)
    
    def add_seq_char_layout(self, seq_char):
        layout_char = qw.QHBoxLayout()
        layout_char.addWidget(qw.QLabel(seq_char))
        delete_button = qw.QPushButton("Remove")
        delete_button.setToolTip("Remove this step of the password sequence.")
        delete_button.clicked.connect(lambda x: self.remove_sequence_character(layout_char))
        layout_char.addWidget(delete_button)
        self.layout_seq_list.addLayout(layout_char)

    def add_sequence_character(self):
        new_seq_char = self.add_character_dropdown.currentText()
        self.group_field.passwords[self.char_label][0].append(new_seq_char)
        self.add_seq_char_layout(new_seq_char)

    def remove_sequence_character(self, char_layout):
        layout_idx = -1
        for i in range(self.layout_seq_list.count()):
            if self.layout_seq_list.itemAt(i) == char_layout:
                layout_idx = i
                break
        if layout_idx != -1:
            self.layout_seq_list.removeItem(char_layout)
            self.group_field.passwords[self.char_label][0].pop(layout_idx)
            deleteLayout(char_layout)
        
    def update_spawn_message(self):
        self.group_field.passwords[self.char_label][1] = self.spawn_message_box.text()

class SaveWindow(qw.QDialog):
    def __init__(self, board_script, nickname, image_url, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.board_script = board_script

        self.setMinimumWidth(640)
        
        layout = qw.QVBoxLayout()

        script_label = qw.QLabel("Board Script")
        script_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(script_label)
        script_display = qw.QPlainTextEdit()
        script_display.setToolTip("A preview of the script portion of the board.")
        script_display.setPlainText(board_script)
        script_display.setReadOnly(True)
        layout.addWidget(script_display)

        properties_label = qw.QLabel("--- Properties for full Board Object ---")
        properties_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(properties_label)
        layout_properties = qw.QHBoxLayout()
        layout_properties.addStretch()

        url_label = qw.QLabel("Board Image URL")
        layout_properties.addWidget(url_label)
        url_label.setToolTip("The URL where the board image is hosted; unfortunately needs to be uploaded separately if you've been working with a local image file.")
        self.image_box = qw.QLineEdit()
        self.image_box.setText(image_url)
        layout_properties.addWidget(self.image_box)
        name_label = qw.QLabel("Object Name")
        layout_properties.addWidget(name_label)
        name_label.setToolTip("The name of the TTS board object.")
        self.nickname_box = qw.QLineEdit()
        self.nickname_box.setText(nickname)
        layout_properties.addWidget(self.nickname_box)

        layout_properties.addStretch()
        layout.addLayout(layout_properties)

        self.button_box = qw.QDialogButtonBox(
            qw.QDialogButtonBox.StandardButton.Save | \
            qw.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout.addWidget(self.button_box)
        self.setLayout(layout)

class MainWindow(qw.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Exceed Custom Board Editor")
        self.setMinimumSize(1280, 960)
        self.setAcceptDrops(True)

        self.board_nickname = ""
        self.board_image_url = ""

        layout_sections = qw.QVBoxLayout()

        self.board_image = BoardImageUpload(self.update_board_image, self.load_board_json, self.clear)
        self.board_image.setFixedHeight(480)
        layout_sections.addWidget(self.board_image)

        layout_globals = qw.QHBoxLayout()
        default_button_label = qw.QLabel('Default Button Size - ')
        layout_globals.addWidget(default_button_label)
        default_button_label.setToolTip("The default height and width for new buttons; if most of your buttons are the same size, it's recommended to have this match that.")

        layout_globals.addWidget(qw.QLabel('w: '))
        self.default_button_w = 100
        self.default_button_w_spinner = qw.QSpinBox()
        self.default_button_w_spinner.setMinimum(0)
        self.default_button_w_spinner.setMaximum(1000)
        self.default_button_w_spinner.setSingleStep(10)
        self.default_button_w_spinner.setValue(self.default_button_w)
        self.default_button_w_spinner.valueChanged.connect(self.update_default_button_w)
        layout_globals.addWidget(self.default_button_w_spinner)

        layout_globals.addWidget(qw.QLabel('h: '))
        self.default_button_h = 100
        self.default_button_h_spinner = qw.QSpinBox()
        self.default_button_h_spinner.setMinimum(0)
        self.default_button_h_spinner.setMaximum(1000)
        self.default_button_h_spinner.setSingleStep(10)
        self.default_button_h_spinner.setValue(self.default_button_h)
        self.default_button_h_spinner.valueChanged.connect(self.update_default_button_h)
        layout_globals.addWidget(self.default_button_h_spinner)
        layout_globals.addStretch()
        layout_sections.addLayout(layout_globals)

        layout_group_wrapper = qw.QVBoxLayout()
        layout_group_wrapper.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.group_id_counter = 0
        self.group_widgets : list[GroupField] = []
        self.group_layout_group = qw.QVBoxLayout()
        layout_group_wrapper.addLayout(self.group_layout_group)
        
        self.add_group_button = qw.QPushButton('(Set a Board Image before adding groups)')
        self.add_group_button.setEnabled(False)
        self.add_group_button.clicked.connect(lambda: self.add_group(False))
        layout_group_wrapper.addWidget(self.add_group_button)
        layout_sections.addLayout(layout_group_wrapper)

        layout_char_wrapper = qw.QVBoxLayout()
        layout_char_wrapper.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.char_id_counter = 0
        self.char_widgets : list[CharacterField] = []
        self.character_layout_group = qw.QVBoxLayout()
        layout_char_wrapper.addLayout(self.character_layout_group)
        
        self.add_character_button = qw.QPushButton('(Set a Board Image before adding characters)')
        self.add_character_button.setEnabled(False)
        self.add_character_button.clicked.connect(lambda: self.add_group(True))
        layout_char_wrapper.addWidget(self.add_character_button)
        layout_sections.addLayout(layout_char_wrapper)

        layout_sections.addStretch()
        
        layout_build = qw.QHBoxLayout()
        layout_build.addStretch()
        self.build_button = qw.QPushButton('Build Board')
        self.build_button.setToolTip("Prepare the board to be exported as a TTS object.")
        self.build_button.setEnabled(False)
        self.build_button.clicked.connect(self.buildScript)
        layout_build.addWidget(self.build_button)
        layout_build.addStretch()
        
        layout_sections.addLayout(layout_build)

        widget = qw.QWidget()
        widget.setLayout(layout_sections)

        self.scroll_area = qw.QScrollArea()
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(widget)

        self.setCentralWidget(self.scroll_area)

    def clear(self):
        for i in range(self.group_layout_group.count()-1, -1, -1):
            target_item = self.group_layout_group.itemAt(i)
            self.group_layout_group.removeItem(target_item)
            deleteLayout(target_item.layout())
            target_item.widget().deleteLater()
        for i in range(self.character_layout_group.count()-1, -1, -1):
            target_item = self.character_layout_group.itemAt(i)
            self.character_layout_group.removeItem(target_item)
            deleteLayout(target_item.layout())
            target_item.widget().deleteLater()

        self.group_widgets.clear()
        self.char_widgets.clear()
        self.board_image.clear()

    def load_board_json(self, parse_dict):
        try:
            response = requests.get(parse_dict[PARSEDICT_IMAGE_URL], headers = {'User-agent': 'bgui-loader'})
            data = qg.QPixmap()
            data.loadFromData(response.content)
            self.board_image.open_image_from_data(data)
        except:
            qw.QMessageBox.critical(self, 'Error', 
                                    'Failed to load board image from URL.')
            return
        
        char_coord_map = parse_dict[PARSEDICT_CHAR_COORDS]
        char_resize_map = parse_dict[PARSEDICT_CHAR_RESIZE]
        char_tooltip_map = parse_dict[PARSEDICT_CHAR_TOOLTIPS]
        char_collection_map = parse_dict[PARSEDICT_CHAR_COLLECTIONS]
        char_json_map = parse_dict[PARSEDICT_CHAR_JSONS]

        self.default_button_w = int(parse_dict[PARSEDICT_BUTTON_WIDTH] // BUTTON_SIZE_FACTOR)
        self.default_button_h = self.default_button_w

        group_defs = []
        for char_def in parse_dict[PARSEDICT_CHAR_DEFS]:
            if char_def in char_collection_map:
                group_defs.append(char_def)
                continue

            self.add_group(True)
            new_char = self.char_widgets[-1]
            new_char.id_entry.setText(char_def)
            new_char.char_label_entry.setText(char_tooltip_map.get(char_def, "").replace('\\\'', '\''))
            if char_def in char_coord_map:
                button_pos = char_coord_map[char_def]
                new_char.x_spinner.setValue(button_pos[0])
                new_char.y_spinner.setValue(button_pos[1])
                if char_def in char_resize_map:
                    button_size_scaling = char_resize_map[char_def]
                    new_char.w_spinner.setValue(int(button_size_scaling[0] * self.default_button_w))
                    new_char.h_spinner.setValue(int(button_size_scaling[1] * self.default_button_w))
            else:
                new_char.hide_on_board_checkbox.setChecked(True)
                new_char.set_hide_on_board(True)
            new_char.char_json_entry.char_json_entry.setPlainText(char_json_map[char_def])
        
        for group_def in group_defs:
            self.add_group(False)
            new_group = self.group_widgets[-1]
            new_group.id_entry.setText(group_def)
            new_group.char_label_entry.setText(char_tooltip_map.get(group_def, "").replace('\\\'', '\''))

            button_pos = char_coord_map[group_def]
            new_group.x_spinner.setValue(button_pos[0])
            new_group.y_spinner.setValue(button_pos[1])
            if group_def in char_resize_map:
                button_size_scaling = char_resize_map[group_def]
                new_group.w_spinner.setValue(int(button_size_scaling[0] * self.default_button_w))
                new_group.h_spinner.setValue(int(button_size_scaling[1] * self.default_button_w))
            char_defs, group_color, group_passwords, group_btn_funcs, group_weights = char_collection_map[group_def]
            
            for i in range(new_group.member_selection.count()):
                char_item = new_group.member_selection.itemText(i)
                if char_item in char_defs:
                    new_group.member_selection.model().item(i).setCheckState(Qt.Checked)

            color = qg.QColor()
            color.setRgbF(*group_color)
            new_group.select_color(color=color)

            for password_char in group_passwords:
                new_group.passwords[password_char] = [group_passwords[password_char][0], group_passwords[password_char][1].replace('\\\'', '\'')]

            # only changing if they don't match defaults
            if group_btn_funcs[0] == True:
                new_group.left_click_random_button.click()
            if group_btn_funcs[1] == False:
                new_group.right_click_group_button.click()

            for weight_char in group_weights:
                new_group.random_char_weights[weight_char] = group_weights[weight_char]

        # Do at the end so update_board_image doesn't overwrite
        self.board_nickname = parse_dict[PARSEDICT_NICKNAME]
        self.board_image_url = parse_dict[PARSEDICT_IMAGE_URL]

    def update_board_image(self):
        self.board_image_url = ""
        for group_widget in self.char_widgets + self.group_widgets:
            group_widget.update_board_image(self.board_image.pixmap)
        self.add_character_button.setText('Add Character')
        self.add_character_button.setToolTip("Add data for a new character.")
        self.add_character_button.setEnabled(True)
        self.add_group_button.setText('Add Group/Random Button')
        self.add_group_button.setToolTip("Add data for a collection of characters that have an associated random and/or group spawn button.")
        self.add_group_button.setEnabled(True)
        self.build_button.setEnabled(True)
        if self.board_image.pixmap:
            self.default_button_w_spinner.setMaximum(self.board_image.pixmap.width())
            self.default_button_h_spinner.setMaximum(self.board_image.pixmap.height())

    def add_group(self, add_char : bool):
        new_frame = qw.QFrame()
        new_frame.setMaximumHeight(200)
        new_frame.setStyleSheet(
            "QFrame {" + \
            "   border: 2px solid #ccc;" + \
            "}"
        )

        new_group = qw.QHBoxLayout()
        new_widget = None
        if add_char:
            new_widget = CharacterField(f"char_{self.char_id_counter}", self.board_image.pixmap, (self.default_button_w, self.default_button_h))
        else:   
            new_widget = GroupField(f"group_{self.group_id_counter}", self.board_image.pixmap,
                                    (self.default_button_w, self.default_button_h), self.char_widgets)
        
        new_widget.setStyleSheet(
            "QFrame {" + \
            "   border: none;" + \
            "}"
        )
        self.char_widgets.append(new_widget) if add_char else self.group_widgets.append(new_widget)
        new_group.addWidget(new_widget)

        delete_button = qw.QPushButton(qg.QIcon(CROSS_BUTTON_PATH), '')
        delete_button.setToolTip("Delete this character/group.")
        delete_button.clicked.connect(lambda: self.delete_group(add_char, new_frame, new_widget))
        new_group.addWidget(delete_button)

        new_frame.setLayout(new_group)
        if add_char:
            self.character_layout_group.addWidget(new_frame)
            self.char_id_counter += 1
            for group in self.group_widgets:
                group.add_char(new_widget)
        else:
            self.group_layout_group.addWidget(new_frame)
            self.group_id_counter += 1

    def delete_group(self, is_char, target_group, target_widget):
        if is_char:
            self.char_widgets.remove(target_widget)
            self.character_layout_group.removeWidget(target_group)
            for group in self.group_widgets:
                group.delete_char(target_widget)
        else:
            target_widget.disconnect_rename_signals()
            self.group_widgets.remove(target_widget)
            self.group_layout_group.removeWidget(target_group)
        deleteLayout(target_group.layout())
        del target_group

    def update_default_button_w(self, new_w):
        self.default_button_w = new_w
    
    def update_default_button_h(self, new_h):
        self.default_button_h = new_h

    def dragEnterEvent(self, a0: qg.QDragEnterEvent | None) -> None:
        if a0 is None:
            return
        a0.accept()

    def dropEvent(self, a0: qg.QDropEvent | None) -> None:
        if a0 is None:
            return
        
        pos = a0.pos()
        widget = a0.source()
        if not isinstance(widget, BoardButtonField):
            return

        widget_list = None
        layout_group = None
        if widget in self.group_widgets:
            widget_list = self.group_widgets
            layout_group = self.group_layout_group
        else:
            widget_list = self.char_widgets
            layout_group = self.character_layout_group

        original_index = widget_list.index(widget)
        original_widget = layout_group.itemAt(original_index).widget() # type: ignore
        insert_index = None
        
        for i in range(layout_group.count()):
            cw = layout_group.itemAt(i).widget() # type: ignore
            cw_center = cw.y() + (cw.size().height()) - self.scroll_area.verticalScrollBar().value() # type: ignore
            if pos.y() < cw_center:
                insert_index = i
                break
        
        widget_list.pop(original_index)
        if insert_index is not None:
            layout_group.insertWidget(insert_index, original_widget) # type: ignore
            ofs = 0 if insert_index > original_index else 0
            widget_list.insert(insert_index + ofs, widget)
        else:
            layout_group.addWidget(original_widget)
            widget_list.append(widget)
        
        a0.accept()

    def buildScript(self):
        try:
            self.build_button.setEnabled(False)
            # Make list of char/group IDs; make sure they're unique
            all_ids = [c.id for c in self.char_widgets] + [g.id for g in self.group_widgets]
            if len(all_ids) != len(set(all_ids)):
                qw.QMessageBox.critical(self, 'Error', 
                                        'One or more Characters and/or Groups have the same ID; make sure they\'re unique and try again.')
                return

            id_def_strings = [f"{id} = '{id}'" for id in all_ids]
            script_id_definitions = '\n'.join(id_def_strings)

            # Make list of jsons; do this early to catch errors
            json_strings = []
            for char in self.char_widgets:
                try:
                    json_strings.append(f"{char.id} = [[{char.get_parsed_json()}]]")
                except:
                    qw.QMessageBox.critical(self, 'Error', 
                                            f'Failed to parse the json for {char.id}. Make sure you\'re providing the full JSON as exported from TTS.')
                    return
            script_json_map = \
                "char_json_map = {\n" + \
                "\t" + ',\n\t'.join(json_strings) + \
                "\n}"
            
            # Make list of button positions and sizes
            button_coordinate_strings = []
            button_size_strings = []
            for widget in self.char_widgets + self.group_widgets:
                if widget.hide_on_board:
                    continue
                button_coordinate_strings.append(f"{widget.id} = {{{widget.button_x}, {widget.button_y}}}")
                if widget.button_size != (self.default_button_w, self.default_button_h):
                    adjusted_w = widget.button_size[0] / self.default_button_w
                    adjusted_h = widget.button_size[1] / self.default_button_w #intentionally width here, since script assumes squares
                    button_size_strings.append(f"{widget.id} = {{{adjusted_w}, {adjusted_h}}}")

            script_coordinate_map = \
                "character_coordinate_map = {\n" + \
                "\t" + ',\n\t'.join(button_coordinate_strings) + \
                "\n}"
            script_resize_map = \
                "button_resize_map = {\n" + \
                "\t" + ',\n\t'.join(button_size_strings) + \
                "\n}"

            # Make list of labels
            label_strings = [f"{char.id} = '{char.char_label.replace('\'', '\\\'')}'" for char in self.char_widgets + self.group_widgets]
            script_tooltip_map = \
                "character_tooltip_map = {\n" + \
                "\t" + ',\n\t'.join(label_strings) + \
                "\n}"

            # Make list of groups (remember bag color is in 0-1 space)
            group_strings = []
            for group in self.group_widgets:
                char_list = group.member_selection.currentTextList()
                bag_color = group.bag_color.getRgbF()
                group_string = \
                    f"{group.id} = {{\n" + \
                    f"\t\tcharacters = {{{', '.join(char_list)}}},\n" + \
                    f"\t\tcolor_string = [[{{\n" + \
                    f"\t\t\t\"r\": {bag_color[0]:.4f},\n" + \
                    f"\t\t\t\"g\": {bag_color[1]:.4f},\n" + \
                    f"\t\t\t\"b\": {bag_color[2]:.4f}\n" + \
                    "\t\t}]],\n"
                
                if group.passwords:
                    group_string += "\t\tpasswords = {\n"
                    pw_strings = []
                    for pw_char in group.passwords:
                        pw_string  = f"\t\t\t{pw_char} = {{\n"
                        pw_string += f"\t\t\t\tsequence = {{{", ".join(group.passwords[pw_char][0])}}},\n"
                        pw_string += f"\t\t\t\tmessage = '{group.passwords[pw_char][1].replace('\'', '\\\'')}'\n"
                        pw_string += f"\t\t\t}}"
                        pw_strings.append(pw_string)
                    group_string += ',\n'.join(pw_strings)
                    group_string += "\n\t\t},\n"

                if group.random_char_weights:
                    group_string += "\t\trandom_weights = {\n"
                    rw_strings = []
                    for rw_char in group.random_char_weights:
                        if group.random_char_weights[rw_char] == 1:
                            continue
                        rw_strings.append(f"\t\t\t{rw_char} = {group.random_char_weights[rw_char]}")
                    group_string += ',\n'.join(rw_strings)
                    group_string += "\n\t\t},\n"

                group_string += f"\t\tleft_click_spawn_random = {'true' if group.left_click_spawns_random else 'false'},\n"
                group_string += f"\t\tright_click_spawn_random = {'true' if group.right_click_spawns_random else 'false'}\n"
                
                group_string += "\t}"
                
                group_strings.append(group_string)
            script_collection_map = \
                "character_collection_map = {\n" + \
                "\t" + ',\n\t'.join(group_strings) + \
                "\n}"
            
            # Set preamble strings
            script_preamble = \
                f"board_image_factor = 11/12\n" + \
                f"image_dimensions = Vector({self.board_image.pixmap.width()}, 0, {self.board_image.pixmap.height()})\n" + \
                f"button_width = {int(self.default_button_w * BUTTON_SIZE_FACTOR)}\n" + \
                f"debug_button_visible = 0\n"

            # Assemble full script - prepend these fields with tags so they can be parsed later

            full_script = \
                f"{BOARD_VERSION_PREFIX} {BOARD_PARSE_VERSION}\n" + \
                f"{BGUI_SECTION_PREAMBLE}\n{script_preamble}\n" + \
                f"{BGUI_SECTION_DEFINITIONS}\n{script_id_definitions}\n" + \
                f"{BGUI_SECTION_COORDINATES}\n{script_coordinate_map}\n" + \
                f"{BGUI_SECTION_RESIZE}\n{script_resize_map}\n" + \
                f"{BGUI_SECTION_TOOLTIPS}\n{script_tooltip_map}\n" + \
                f"{BGUI_SECTION_COLLECTIONS}\n{script_collection_map}\n" + \
                f"{BGUI_SECTION_JSONS}\n{script_json_map}\n" + \
                f"{BGUI_SECTION_BODY}\n"
            
            with open(SCRIPT_BODY_PATH, 'r') as f:
                full_script += f.read()

            save_dialog = SaveWindow(full_script, self.board_nickname, self.board_image_url)
            if save_dialog.exec():
                # Assemble full object
                self.board_nickname = json.dumps(save_dialog.nickname_box.text())
                self.board_image_url = save_dialog.image_box.text()

                board_script = json.dumps(full_script)

                board_object = ""
                with open(OBJECT_TEMPLATE_PATH, 'r') as f:
                    board_object = f.read()

                board_object = board_object.replace(
                        BGUI_INSERT_NICKNAME, self.board_nickname
                    ).replace(
                        BGUI_INSERT_IMAGE, self.board_image_url
                    ).replace(
                        BGUI_INSERT_SCRIPT, board_script)
                
                board_filename = qw.QFileDialog.getSaveFileName(self, "Save Board JSON", "", "JSON Files (*.json)")
                if board_filename[0]:
                    with open(board_filename[0], 'w') as f:
                        f.write(board_object)

                    done_dialog = qw.QMessageBox(self)
                    done_dialog.setWindowTitle("Saved!")
                    done_dialog.setText(f"Board file saved to {board_filename[0]}.")
                    done_dialog.exec()
        finally:
            self.build_button.setEnabled(True)


def deleteLayout(layout):
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                deleteLayout(item.layout())
        sip.delete(layout)

app = qw.QApplication([])

window = MainWindow()
window.show()

app.exec()

print('bye')