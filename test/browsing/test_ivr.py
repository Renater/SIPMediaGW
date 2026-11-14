"""
The IVR opens its page in the gateway's Chrome, waits there for a platform and
a room (from the keypad, the SIP URI or the phone), shows the pairing code and
QR code, and then hands the room to the platform's browsing script. Chrome and
the gateway's files are replaced here: these tests cover the IVR's own logic.
"""
import json
import os
import queue
import sys
import types
from typing import ClassVar
from unittest.mock import MagicMock, mock_open, patch

import pytest

RUNTIME_ONLY = ("qrcode", "requests", "selenium", "selenium.webdriver",
                "selenium.webdriver.chrome", "selenium.webdriver.chrome.service",
                "selenium.webdriver.support", "selenium.webdriver.support.ui")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
with patch.dict(sys.modules, {name: MagicMock() for name in RUNTIME_ONLY if name not in sys.modules}):
    import ivr as ivr_module


class Options:
    """The part of selenium's ChromeOptions the IVR uses."""
    def __init__(self):
        self.arguments = []
        self.experimental_options = {}

    def add_argument(self, argument):
        self.arguments.append(argument)

    def add_experimental_option(self, name, value):
        self.experimental_options[name] = value


def new_ivr(**kwargs):
    # A fresh Options per IVR: the replaced selenium hands out one shared mock.
    with patch.object(ivr_module.os, "makedirs", side_effect=OSError("read-only")), \
            patch.object(ivr_module.webdriver, "ChromeOptions", Options):
        return ivr_module.IVR(**kwargs)


@pytest.fixture
def ivr(monkeypatch):
    monkeypatch.delenv("AUDIO_ONLY", raising=False)
    monkeypatch.delenv("IVR_TIMEOUT", raising=False)
    instance = new_ivr(width=1280, height=720, name="Room 2.14")
    instance.chromeOptions = Options()
    instance.driver = MagicMock()
    return instance


def scripted_driver(browsing=None, room=None, limit=200):
    """
    A driver whose page reports browsing and room as the IVR page does. It
    answers at most limit times, so that a broken loop fails instead of hanging.
    """
    driver = MagicMock()
    browsing = list(browsing or [])
    room = list(room or [])
    calls = []

    def execute(script, *args):
        calls.append(script)
        if len(calls) > limit:
            raise AssertionError("the IVR page was polled too often")
        if script == "return window.browsing":
            return browsing.pop(0) if browsing else None
        if script == "return window.room":
            return room.pop(0) if room else None
        return None
    driver.execute_script.side_effect = execute
    return driver


class TestConstruction:
    def test_audio_only_runs_chrome_headless(self, monkeypatch):
        monkeypatch.setenv("AUDIO_ONLY", "true")
        instance = new_ivr(width=640, height=360)
        assert "--headless=new" in instance.chromeOptions.arguments
        assert "--use-fake-ui-for-media-stream" in instance.chromeOptions.arguments
        assert "--window-size=640,360" in instance.chromeOptions.arguments

    def test_not_headless_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_ONLY", raising=False)
        instance = new_ivr(width=1280, height=720)
        assert "--headless=new" not in instance.chromeOptions.arguments
        assert "--window-size=1280,720" in instance.chromeOptions.arguments
        assert "--autoplay-policy=no-user-gesture-required" in instance.chromeOptions.arguments

    def test_ivr_timeout_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("IVR_TIMEOUT", "900")
        assert new_ivr(width=640, height=360).IVRTimeout == 900

    def test_no_ivr_timeout_by_default(self, monkeypatch):
        monkeypatch.delenv("IVR_TIMEOUT", raising=False)
        assert new_ivr(width=640, height=360).IVRTimeout is None

    def test_writes_the_chrome_policy(self):
        written = mock_open()
        with patch.object(ivr_module.os, "makedirs") as makedirs, \
                patch("builtins.open", written), \
                patch.object(ivr_module.webdriver, "ChromeOptions", Options):
            ivr_module.IVR(width=640, height=360)
        makedirs.assert_called_once_with("/etc/opt/chrome/policies/managed", exist_ok=True)
        written.assert_called_once_with("/etc/opt/chrome/policies/managed/managed_policies.json", "w")
        written().write.assert_called_once_with('{ "CommandLineFlagSecurityWarningsEnabled": false }')


class TestBrowserLanguage:
    @pytest.mark.parametrize("lang, locale", [
        ("fr", "fr-FR"), ("en", "en-US"), ("de", "de-DE"),
        ("pt", "pt-PT"), ("pt-br", "pt-br"), (" FR ", "fr-FR"), (None, "en-US"),
    ])
    def test_locale(self, ivr, lang, locale):
        ivr.applyBrowserLanguage(lang)
        assert ivr.chromeOptions.arguments == [f"--lang={locale}"]
        normalized = (lang or "en").strip().lower()
        assert ivr.chromeOptions.experimental_options["prefs"]["intl.accept_languages"] == f"{locale},{normalized}"

    def test_keeps_the_other_preferences(self, ivr):
        ivr.chromeOptions.experimental_options["prefs"] = {"keep": 1}
        ivr.applyBrowserLanguage("fr")
        assert ivr.chromeOptions.experimental_options["prefs"]["keep"] == 1


class TestSetUrl:
    def test_url_carries_what_is_known(self, ivr):
        ivr.roomName = "lecture1"
        ivr.browsingId = "2"
        ivr.browsingName = "edumeet"
        ivr.mixedId = "2.lecture 1"
        config = {"lang": "fr", "webrtc_domains": {}}
        with patch("builtins.open", mock_open(read_data=json.dumps(config))):
            ivr.setUrl()
        assert ivr.url.startswith("file://")
        assert ivr.url.split("?")[0].endswith("browsing/assets/IVR/index.html")
        assert "displayName=Room%202.14" in ivr.url
        assert "&roomId=lecture1" in ivr.url
        assert "&domainId=2" in ivr.url
        assert "&domainKey=edumeet" in ivr.url
        assert "&mixedId=2.lecture%201" in ivr.url
        assert ivr.config == config
        assert ivr.chromeOptions.arguments == ["--lang=fr-FR"]

    def test_url_without_room_or_platform(self, ivr):
        with patch("builtins.open", mock_open(read_data="{}")):
            ivr.setUrl()
        assert "roomId" not in ivr.url and "domainId" not in ivr.url
        assert "domainKey" not in ivr.url and "mixedId" not in ivr.url
        assert ivr.chromeOptions.arguments == ["--lang=en-US"]


class TestLaunchBrowser:
    def test_opens_the_ivr_page_in_chromedriver(self, ivr):
        ivr.driver = None
        driver = MagicMock()

        def set_url():
            ivr.url = "file:///ivr/index.html?displayName=x"
        with patch.object(ivr, "setUrl", side_effect=set_url), \
                patch.object(ivr_module.webdriver, "Remote", return_value=driver) as remote:
            ivr.launchBrowser()
        assert remote.call_args.kwargs["command_executor"] == "http://127.0.0.1:9515"
        assert remote.call_args.kwargs["options"] is ivr.chromeOptions
        driver.get.assert_called_once_with("file:///ivr/index.html?displayName=x")

    def test_reuses_the_driver_and_takes_a_given_url(self, ivr):
        def set_url():
            ivr.url = "file:///ivr/index.html"
        with patch.object(ivr, "setUrl", side_effect=set_url), \
                patch.object(ivr_module.webdriver, "Remote") as remote:
            ivr.launchBrowser("https://meet.example.org/room")
        remote.assert_not_called()
        ivr.driver.get.assert_called_once_with("https://meet.example.org/room")

    def test_a_failure_does_not_raise(self, ivr):
        with patch.object(ivr, "setUrl", side_effect=FileNotFoundError("config.json")):
            ivr.launchBrowser()
        ivr.driver.get.assert_not_called()

    def test_nothing_to_open_without_a_url(self, ivr):
        def no_url():
            ivr.url = ""
        with patch.object(ivr, "setUrl", side_effect=no_url):
            ivr.launchBrowser()
        ivr.driver.get.assert_not_called()


class TestInteract:
    def test_a_key_reaches_the_page(self, ivr):
        ivr.userInputs.put("5")
        ivr.interact()
        ivr.driver.execute_script.assert_called_once_with(
            "document.dispatchEvent(new KeyboardEvent('keydown',{'key':'5'}));")

    def test_nothing_without_a_key(self, ivr):
        ivr.userInputs = queue.Queue()
        ivr.interact()
        ivr.driver.execute_script.assert_not_called()


class TestPrompt:
    def test_returns_the_platform_and_the_room(self, ivr):
        room = {"roomName": "lecture1", "config": {"webrtc_domain": "meet.example.org"}}
        ivr.driver = scripted_driver(browsing=[None, "edumeet.example.org"], room=[None, room])
        with patch.object(ivr, "readPairingCode"):
            assert ivr.prompt() == ("edumeet.example.org", room)
        menu = os.path.join(os.path.dirname(__file__), "../../browsing/assets/IVR/menu.js")
        with open(menu, encoding="utf-8") as f:
            assert ivr.driver.execute_script.call_args_list[0].args[0] == f.read()

    def test_forwards_keys_while_waiting(self, ivr):
        room = {"roomName": "lecture1"}
        ivr.driver = scripted_driver(browsing=["jitsi"], room=[None, room])
        ivr.userInputs.put("#")
        with patch.object(ivr, "readPairingCode"):
            ivr.prompt()
        scripts = [c.args[0] for c in ivr.driver.execute_script.call_args_list]
        assert "document.dispatchEvent(new KeyboardEvent('keydown',{'key':'#'}));" in scripts

    def test_gives_up_after_the_ivr_timeout(self, ivr):
        # The page is never asked once the time is up. Asking it raises, so that
        # an IVR that ignored its timeout fails here instead of waiting forever.
        def execute(script, *args):
            if script == "return window.browsing":
                raise AssertionError("polled after the IVR timeout")
        ivr.IVRTimeout = 1
        ivr.driver.execute_script.side_effect = execute
        with patch.object(ivr, "readPairingCode"), \
                patch.object(ivr_module.time, "time", side_effect=[0, 5, 5, 5]):
            assert ivr.prompt() == {}
        scripts = [c.args[0] for c in ivr.driver.execute_script.call_args_list]
        assert "return window.browsing" not in scripts

    def test_a_page_error_ends_the_prompt(self, ivr):
        def execute(script, *args):
            if script == "return window.browsing":
                raise RuntimeError("page gone")
        ivr.driver.execute_script.side_effect = execute
        with patch.object(ivr, "readPairingCode"):
            assert ivr.prompt() == {}


class TestRun:
    def test_closes_the_ivr_and_attends_the_room(self, ivr):
        room = {"roomName": "lecture1"}
        driver = ivr.driver
        with patch.object(ivr, "launchBrowser"), \
                patch.object(ivr, "prompt", return_value=("Edumeet Example", room)), \
                patch.object(ivr, "attend") as attend:
            ivr.run()
        driver.close.assert_called_once()
        driver.quit.assert_called_once()
        attend.assert_called_once_with(room)
        assert ivr.browsingKey == "Edumeet Example"
        assert ivr.browsingName == "edumeetexample"
        assert ivr.roomName == "lecture1"

    def test_no_room_attends_nothing(self, ivr):
        driver = ivr.driver
        with patch.object(ivr, "launchBrowser"), \
                patch.object(ivr, "prompt", return_value={}), \
                patch.object(ivr, "attend") as attend:
            assert ivr.run() == {}
        attend.assert_not_called()
        driver.quit.assert_not_called()


class TestAttend:
    def test_a_script_without_a_class_is_refused(self, ivr):
        ivr.config = {"webrtc_domains": {"x": {"browsing": "emptyconnector"}}}
        ivr.browsingKey = "x"
        with patch.dict(sys.modules, {"emptyconnector": types.ModuleType("emptyconnector")}), \
                pytest.raises(ImportError, match="No class found in emptyconnector"):
            ivr.attend({"roomName": "lecture1"})


class FakeQRCode:
    """Stands for qrcode.QRCode: records the data and writes a known image."""
    data: ClassVar[list] = []

    def __init__(self, **kwargs):
        pass

    def add_data(self, data):
        FakeQRCode.data.append(data)

    def make(self, fit=True):
        pass

    def make_image(self, **kwargs):
        image = MagicMock()
        image.save.side_effect = lambda buffer, format: buffer.write(b"PNG-IMAGE")
        return image


class TestPairingCode:
    ENV = 'PATH=/usr/bin\nPAIRING_CODE="ABCDE"\n'

    def test_injects_the_code_and_the_qr_code(self, ivr, monkeypatch):
        monkeypatch.setenv("GW_PROXY", "http://10.0.0.10:9000")
        monkeypatch.setenv("GW_REVERSE_PROXY", "https://sip.example.org")
        monkeypatch.setenv("QR_CODE_URL", "{reverse_proxy}/?pairingCode={code}")
        driver = MagicMock()
        driver.execute_script.return_value = None
        FakeQRCode.data = []
        with patch("builtins.open", mock_open(read_data=self.ENV)), \
                patch.object(ivr_module.qrcode, "QRCode", FakeQRCode):
            ivr.readPairingCode(driver)
        injected = [c for c in driver.execute_script.call_args_list
                    if c.args[0] == "window.pairingInfo = arguments[0];"]
        assert len(injected) == 1
        info = injected[0].args[1]
        assert info["pairingCode"] == "ABCDE"
        assert info["pairingUrl"] == "https://sip.example.org/"
        assert FakeQRCode.data == ["https://sip.example.org/?pairingCode=ABCDE"]
        assert info["qrCodeB64"] == "UE5HLUlNQUdF"  # base64 of b"PNG-IMAGE"
        assert driver.execute_script.call_args_list[-1].args[0] == "window.updateQrCode();"

    def test_falls_back_to_the_proxy_address(self, ivr, monkeypatch):
        monkeypatch.setenv("GW_PROXY", "http://10.0.0.10:9000")
        monkeypatch.delenv("GW_REVERSE_PROXY", raising=False)
        monkeypatch.setenv("QR_CODE_URL", "{reverse_proxy}/?pairingCode={code}")
        driver = MagicMock()
        driver.execute_script.return_value = None
        with patch("builtins.open", mock_open(read_data=self.ENV)):
            ivr.readPairingCode(driver)
        info = next(c for c in driver.execute_script.call_args_list
                    if c.args[0] == "window.pairingInfo = arguments[0];").args[1]
        assert info["pairingUrl"] == "http://10.0.0.10:9000/"

    def test_same_code_is_not_injected_again(self, ivr, monkeypatch):
        monkeypatch.setenv("GW_PROXY", "http://10.0.0.10:9000")
        monkeypatch.setenv("QR_CODE_URL", "{reverse_proxy}/?pairingCode={code}")
        driver = MagicMock()
        driver.execute_script.return_value = {"pairingCode": "ABCDE"}
        with patch("builtins.open", mock_open(read_data=self.ENV)):
            ivr.readPairingCode(driver)
        driver.execute_script.assert_called_once_with("return window.pairingInfo;")

    def test_without_proxy_the_code_is_cleared(self, ivr, monkeypatch):
        monkeypatch.delenv("GW_PROXY", raising=False)
        monkeypatch.delenv("QR_CODE_URL", raising=False)
        driver = MagicMock()
        driver.execute_script.return_value = None
        with patch("builtins.open", mock_open(read_data=self.ENV)):
            ivr.readPairingCode(driver)
        injected = [c for c in driver.execute_script.call_args_list
                    if c.args[0] == "window.pairingInfo = arguments[0];"]
        assert injected[0].args[1] == {"pairingCode": ""}

    def test_a_missing_environment_file_is_ignored(self, ivr):
        driver = MagicMock()
        with patch("builtins.open", side_effect=FileNotFoundError("/etc/environment")):
            ivr.readPairingCode(driver)
        driver.execute_script.assert_not_called()

    def test_a_qr_code_failure_still_shows_the_code(self, ivr, monkeypatch):
        monkeypatch.setenv("GW_PROXY", "http://10.0.0.10:9000")
        monkeypatch.setenv("QR_CODE_URL", "{reverse_proxy}/?pairingCode={code}")
        driver = MagicMock()
        driver.execute_script.return_value = None
        with patch("builtins.open", mock_open(read_data=self.ENV)), \
                patch.object(ivr_module.qrcode, "QRCode", side_effect=RuntimeError("no PIL")):
            ivr.readPairingCode(driver)
        info = next(c for c in driver.execute_script.call_args_list
                    if c.args[0] == "window.pairingInfo = arguments[0];").args[1]
        assert info["pairingCode"] == "ABCDE"
        assert info["qrCodeB64"] == ""
