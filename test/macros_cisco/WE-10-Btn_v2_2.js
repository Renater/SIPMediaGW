import xapi from 'xapi'; 

/********************************************************
 * SECTION 1: METADATA
 ********************************************************/

const METADATA = {
  name: 'WE',
  version: 'WE-10-Btn_v2_2',
  description: "Webinaire de l'État macro",
};

/********************************************************
 * SECTION 2: CONFIG (SERVICE)
 ********************************************************/

const SERVICE = {
  name: METADATA.name,
  version: METADATA.version,

  panels: {
    home: 'we_button',
    controls: 'we_controls',
    home_icon: 'webe37b94f512d5cdf8f69ec8d9cd5f7e33',
    controls_icon:'webctrl8f237991c7e8f3c04ac5ae94cf7ed2df',
  },
  matching: {
    prefix: '2',
    postfix: '@rdv.visio.renater.fr',
    allowedHost: 'rdv.visio.renater.fr',
    sparkFallback: true,
  },

  features: {
    autoMuteOnJoin: false,
    lockdownUI: true,
    dynamicPanel: false,
    exclusiveToggles: {},
    codecVersionCheck: true,
    micMuteDtmf: '1',
    videoMuteDtmf: '2',
    httpHostAllowed: true,
    reconcileTimer: null,
    reconcileToken: 0,
    participantsOpen: false,
    chatOpen: false,
  },

  dtmf: {
    audio: '1',
    video: '2',
    conversation: '3',
    hand: '4',
    participants: '5',
    enregistrement: '6',
    menu: '#',
  },

  widgets: {
    we_ctrl_hand:           { kind: 'toggle', dtmf: 'hand' },
    we_ctrl_chat:           { kind: 'toggle', dtmf: 'conversation' },
    we_ctrl_participants:   { kind: 'toggle', dtmf: 'participants' },
    we_ctrl_enregistrement: { kind: 'button', dtmf: 'enregistrement' },
    we_ctrl_menu:           { kind: 'button', dtmf: 'menu' },
  },

  input: {
    mode: 'single',
    feedbackId: 'we_meeting',
    inputType: 'SingleLine',
    placeholder: 'Saisissez un code à 10 chiffres.',
    title: "Webinaire de l'État",
    defaultPrompt: "Saisissez l'identifiant de la conférence que vous souhaitez créer ou rejoindre:",
    submitText: 'Appeler',
  },
};

var CALL_SUCCESS_RECONCILE_DELAY_MS = 300;
var PARTICIPANT_RECONCILE_DELAY_MS = 120;
var DISCONNECT_RECONCILE_DELAY_MS = 80;
var BOOT_RECONCILE_DELAY_MS = 250;

const TOGGLE_WIDGET_IDS = Object.keys(SERVICE.widgets)
  .filter(function (id) { return SERVICE.widgets[id].kind === 'toggle'; });

/********************************************************
 * SECTION 2b: PANEL XML
 ********************************************************/

const HOME_PANEL_XML = `<Extensions>
  <Version>1.8</Version>
  <Panel>
    <Order>2</Order>
     <PanelId>${SERVICE.panels.home}</PanelId>
    <Origin>local</Origin>
    <Type>Home</Type>
    <Icon>Custom</Icon>
    <Name>Webinaire de l\'État</Name>
    <ActivityType>Custom</ActivityType>
    <CustomIcon>
      <Content>iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAALzklEQVR42u2ae3Bc1X3Hv79zzr371NqWkLEDLiR2oLVJmhpPU5KmtkJoQ5rQtBPttEyJiQNyCEndxBgcoNy9pTYCYrmmqScWhTSGJJ27tGmbkJZOJlIJgwN1JtOADTE4fsWSbL32pX3cx/n1j9Ua1ZalNd71pFS/P6Xds+dzz+/x/f3OBeZszuZszuZszv7/GTOTZbGwLBbMTG9VTnIcltMBWszCcVhe8A0180SJBAMMAHh45+sLEY8tDLTLOj8xdPfnl4/WPgcARMQXAlg1Y1HLYkFEGgBt2z1ycyQSX8sQ7wHUPDADsWDsK05xr1ssPkpET73xgJoPTc2AtW3S1o4Dl7YvvuTJeEt0tR8AXgXQuvoZIQHTBEgAE7mJfzl+6Cef6v7SB8YvBDQ1GhYAEHtx4cLLf/2HsURoWSEPD4AAQxBV3ZeZGAQNBifmQ2XGyi+8+sqPPtSeWlNMAdxMaNHQ1VKAbZOet3j5Y/F5oWWFHFwCDAIkEaj6fAlEoMm/qVwG7oLW8HuXLV3VYxPpdLrBe2oWsOOwtIn0w48PfzAxP/6RQg4+EcxZXYxg5PMIwtHILVt2Hr0qmaTglKf8MgPva6+GhxGOrpUSjPqdkjgAR2OSIi0LbgQArDmffTE5Dkurj9V05bBhwHaH8AGQJGOl74NA9a/NBAoCQCrjvQCQWgP9JoWNAoiTSQrsDvIncwE1viwxE4i4y9oVYXCb1gCzJiJR5xFr0lpAQLQBAAmh6/1dZzLmiSgA4AOdsmf3ztWxuLlk4OevPW3fsWpkavZvDHDtGQ7Cw69RhQBURUd9VYCrsQyAKwDAWs9YniyLBdZA2ER+EggAoLv3wKXR+MWdUoXWGWboqkgMaLtkxf7ND/z0twFkaofSIOFBbDELm8h7ZM3aQ1LhMtdD3YKZILSUoCDwDgJAqh+yelpnJsZ9nWCbSMOG/qzVF79i2buuk0bkj4Uyfy8aU/N8D3ArCPwcAqnCy0OtsRYiGrcsFjbAjVNa/RAAtOeVnpYq1AENrjeKGSAGyPOK/1pdq/8M0M5O6Em3xUN/f+zdkdCCTwppfCIUMS8TEqiUgGIePgiCGbqlBebwUOar9vqlRx2HZTJZ/W7DhAczEwGwtv24rX3Ju181Q8YC1wVoluTFjCAUhiwWKq+P/WzPu1KpNZWqexNPAWUA2Lb7xIdD4ZbPCmF8JBpTslIBPK/q0lVhA9Ksg3hcyFy2/OLhgZ+sSeSuqaRSb4iZhmVpImInDWHfsWqkVMx8zjAhhAQzT25oelhfSgjWGuXieJdtd5TTaYhOJy2YmZJJCoiItz858kd/my7/MDF/4b9FY5GPMSs5kYfve9AEyJqwYUYQiQg5UagcHDrx2g3bN76vdHpj0nAtXXOfnt3ZL7TMT/QQAZUSNPBGqZlMUiIchfBd38+MZtbddUv7E1279hq7uq4OJhsP9Hx9+A/CsZY7Q6HQ+xhApQzNAFP1oOi0h6cNExT43uiJwWPvtz+/9ECnwzI96cpNbQ9r0FsfPfHh+a3z7jdUaJVh4pQWoerm4fvlZ7Ojo5vv/syle3bsOBDasOGKCgA8/PjgByPxxL3hSLQDAMolaECDSIizeApLBU3kY/Tk8LX3rH/bf1oWK9sm/4L1w1MSBW1/Yni1VKEPAOpXCGAIfdAvF579wtpFewDActi0k+Raf3PwiovaL95ihmOfUAooFWcGnWJ+NAY1cmLstk2favuq1cfK7jgTtqnAp0GfNdGl+iHtDvK3787cFonHukNhlShOnHJdOXuyhN+SgBo5ke3duHb++r4+Vh1ngW068JQxj6hp7ZqtGK56eDJJ+q+/kd81vzV+a6kI+IEOBIm6Rj+aEcRikIVs+fl/3NW9+vbbU5zshMYMooVmr5FMsFIyvX8/d6bTmgBuaHJ7Ive19kUtN+cy8Jihqm1kPWWwmqQ8tzKcOXZk5b0bf/W4ZWlh26QbOgDosyzVD2jbtvX5wn756yPr2he1PVbIwwXP3kr+ryQlEZDw5ejJoWvvWb+kb7bwmRWYq/KWf7p584JWM3GDy97hd9xvPYdJ7cqOI9PpNJLpdHBuuEzMwBd79oQvX3z1z6Jx8xK3XNWX9S8BP9YCdfL42MY7b2nrmSlJ1T/EsywJ2/ZjKrrjkra2m0ayGQzZD7zsBcGT2Yr3LUomj9YST38qJes9dceBIKLgwcdO/mYkZi5xy9Dn1Eoy/HgCanx44pvnCjsz8P79DABeEHw3W8jfBMA3hbpqQTjabcrS3cetLd/O+/rviOi5mtBnyxL9gJgJvpa8lDJXGAbYq0DXq/iYEYQjUIVM+aVXXv/BrY7DsnMNArsRY1pKpwO2LEG27ey7y4ovaok/GmjNoxMTnqFkojUaWxt23bUDqQf2+EHwzeFi6Ttk20dqioqZCamUBKBpGnhpmPF6E1R1Pc3KEOS5XiF7cijZa99QXMwskuc48JuxWyLb1uw4kpLJx1+68y+OL4rH/yEWMudPVFw/ExQJgGgJha5RUl5jStl93Nr6rA/9z9mK930i+vnUk6+td+qHlXkOG2UIEoFhQA0PjH76nj97+6uWxcqm+l257okHJZMBW5Yi237mx3d8afWl8XnfTYTDS3KVciCIqOC6AZihhIi1hMLXC6LrQ1QqD1hb/ysAfy8XBN8h+759NfBUTRp5ZQOI1TvY8OMJqJGhbM/mrsXOucbtmypLk9D+jz638e2Xt7f/R9w0l+UrZZ9AajKrM5g1AEghZNQwoaREtlLyWeOZX+Qz96/a1v2C47xsJpNXuTuf4k3RGB6aqPawajZxkc+Wn91wY6TD6mNhdyCottBNnFqSbft9lqV+6yvbDr00OnBtvlJ5LREKK8261lgTEUkikgEz591yMF4q+qxZJcKh33/Hgrbn9m+2PtrZucIDAK2DejxZmwZEqegOnxg8eiMzM/qh3yzsOffDHbbts+PI6x555OjLY4Mfyrvu64lwRGrm01swIpCkyZDJFktuWCoVN4wtyWRaVIH92byLSUCTYMqPZ27auvHK4+k0ZlVSDZ9LUzIZ1KAPjY1fV6i4R1pCoTOgTwsco+i5LIkWfXzpSKLeEhSNQ2VHx+/f3HXxM1Yfq3qUVFMG8TXoa3Y8ePhALvO7Rc8fjJnmjNCCiADieaeCU8/YFETjUNmx0vc3rWu7r5qkcN6w5zXioWQy6LMs9Ts93QcOZcaud4NgLGIYUmvW08x/mIjAYP/ghBfMGrcmRKngnjwxdPiTzEznG7cNu3noqCWy7Q/+97FM7mOauWgqSYzpbw40sx4LxjQA+L4/LS0JaCFAE9nM2q1fXD7YiLht6FVLh237bFlqZc+W54/kcp0kiA0hWDOfcSJKSi+xdMXkCQfT1ttYHCozln3ozlsv/vdGxW3D75bItv29XV3Gyof/6ntDhcLNIWVIJWTAU3rn6kUpuDXXzmdLUpEoVGa89MKLT996t+OwbFTcNuUybVVvr7e3q8tY0f2XTwzkspsS4ZAinH3DU8swM1gZgFvxC9nMwE3pdDrYt682n/8lBZ4KfWW3/eVj2eyO1mhMcU1P1z50+SnkKTkNQSgEmctmN9x327LXJieOGk2whl88X93b67NlqXdutf58oJD9dmskqqDZB4BAazXy8l5ZxdW1QYMfjUONj078013rLnrc6pt+vNooa/hbPAQwp1IBA6J38NiffnTxZc8lwuHfKPs+tNayUCpQ7YA1A9KAMZH3TpbGDnzGslhUS1DzrCmvFtSuNtb39hYPF4p/WPS8k1HDBEgESyNLGQBCkagLBisJWcrnbr9nw8rhFStAzXLlpgLXet8+y1Lv37blyGAu/ydVtQU6Ufs/w421gPLZQnrTpy96qhkl6IICT63R79m25QfHc5ktgqj9oviS2m1fKJcJvGLx2IY31FTzTTT7B8i2A6ezU37j+f5UwfOeugKvJADAZ789M1rYee/65YOpfshmu3LTktZ0mmLKKHfd2668kQCgWMo7YS78YvJNm3MaxP1fsbfsK8N1Qb/V35ueszmbs+bY/wAL/A3WHePR0AAAAABJRU5ErkJggg==</Content>
      <Id>${SERVICE.panels.home_icon}</Id>
    </CustomIcon>
  </Panel>
</Extensions>`;

function buildControlsPanelXml(placementLine) {
  return `<Extensions>
  <Version>1.8</Version>
  <Panel>
    <Order>1</Order>
    <PanelId>${SERVICE.panels.controls}</PanelId>
    <Origin>local</Origin>
    ${placementLine}
    <Icon>Custom</Icon>
    <Name>Interactions Webinaire</Name>
    <ActivityType>Custom</ActivityType>
    <CustomIcon>
      <Content>iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAAGEElEQVR42u2aW2hcdRDGvzmb2mglUGjWiFLRBxEUEV9EUErFKyiiqCjYenkQq4JU8IIPIqihiD74IuqLWlEQL4ioRCjihd6QxRu+2Iq1VKtVa0Vb0+w55+dD5tTxsJvsJmeTxu7AsrvJucz3n5lvvv+clfrWt771rW99O2zM5upGgIX7YWb87wA7yERSXgYIJJLMzLL/BWDAIkigLqkuCUk/mdlvYVE0XxGvCmxSgAFuAT4E9vGv/Qa8D1xTyoYFDfZEBzqdvQUsXZCggcRfI8A2BzQBpEDebDbJ8xwg9781/ZgtwLF+ri3E6L7rQA52EOHimOf83NpCAVvz9wscQBMgz3PyPCdNU8bGxti7d++hv7kV0c6BM+LCHe6AB/z9RXe+GcM4MTHBkiVL2LJlS6soF8eOxmvNtDsANWCgVXkMVAXYzFK/wdne7hJJStNUBw8e1Pj4uIaGhjQ+Pq79+/erVqtpcHCw3B7P8fd8hj2/ZmappKxde6xSYAg4BvjRI5oDbNiwgXq9zsjICEmSMDw8TL1eZ926dZOhbTYBMo/w5zOMZi2WlpfVTcCynrB/ALwI+A4gy7IMYN++fTQaDTZv3ky9Xmf9+vU0Gg127dpFUeMB8NZOHHQ2Hyj97URgLfBVKJWvgaW+MNYrhv4gENF/bPHixTQajXY1nAOvTFXDHr0kfD8WuAp4tSRs0sD+y6N/AxViTrz23pW00iWkAAFK01Sjo6MaHh5Wnk+WaJIksYZN0ttTdIC80N3AmZJWS7pG0knh0DT4cZSkZ8xsJ1CrXLMXaQMsA371NM066MNFJmwDBmP6eUQt3ONS4O1S9qShrcXrbQWO7qmYCb34+pIzhwgq9N+YygArA8gy0KuBT1qUQdZm8bYDx81JTw+g1wZHMncwvrLg+KpAerFGrwQ2lq4To0npfznwC3DqnKq2APpS4NMp0vkj4Fw/dnE4/wInvwhmqvLIQzatmIr4erkfrplZ5qm5QtL5kpY7mX0r6WMz2+zHHmVmEx6Zx5yMogCZLi1TJ+A1ZvYMMOACZH709TREV0jSNcAfpdTtxApZ+uxsZWmV7F1o2/g6RE7Acy2Ihy4YfmO4plXhcDUXa13nz4d9c94F2IKkfgZO6BkjO/ikIrC3drFvLpNU0dJWVsLIofkvdSG+ooVIr80wY8xFwc4uBEqrur2nsroNZLI+3Ogr4P5Cn5ZSPukyuitCas4E7MuVklRw7LrSjXA2fQE4r9UuZirwYSHvaDUo6JCkvvStaKW8EndAtwaSKNfbJuAu4KQ2ZJe0AXxfi4Wcrm4z4E/gtF6SVBHpS4Dfg5NlifcX8B5wG3BKq2lmCfC9XQIujruu5/02OHmmE01Mr7RF7/wb+Bh4ADi91cYdeLALwMUxT86ZuAiOnhxmzs02erbs7DvAOYWM7DLCadDdSbvhXK9BLwe+mUIZlQftBbDLQ7vrBHDBG3uAE5wXZlW3XZ3sk8mame2UdKGk7ZJqcUoYNiW1MFGZ8M+PhXtOFyV882CSVpnZD5ISM8vnDLCDzgLoiyR93wZ0tEUOYETSUIe3ynyRHjGz930HNOsxzYzSI4DeIeliSbs7AG3FnKsLsBvM7CEvpUpmUjOuBwc9YGbfSLpM0l4HnbdJz2LfOp3jufu1R9Jqr/m8qmH6rAjAa3rAzL6QdIWkAx7JfAoweQeATdJNZra7irqtDHAJ9CZJ13o0aZO+zWkiXEwuHjezsarqtlLAAfQiM3tP0s2hnmmR2kxTt1slPegKr/Lff1SmRc2s6aBfknSvO9+pw8Ui/OUtKFOPfulTqfgOoJ+Q9JSD7mSYlnlW3G1m2zyVcy0EKw3m3ixNNHYAS0q7pb/9/Y250MmVb688DTOXgDdK+syf88ijaC1EyR5Jt/s5+YICHEDLzA5IusoBqURkE/65JulOM/tl8hRbeIAdbO61+L2kG1ro5wn//pqZvd6LFjRfNV3U86PAAWDQv6/10ezxVeyCOrW5mNJn3lMf1uSjliFJ45KGJT1tZrvn7dHIXEQbWOSfz/JnycZC/dlhJ3PuI8pKD7mTI3IR+ta3vs3K/gHmqv3YbucyIwAAAABJRU5ErkJggg==</Content>
      <Id>${SERVICE.panels.controls_icon}</Id>
    </CustomIcon>
    <Page>
      <Name>Webinaire</Name>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_6</WidgetId>
          <Name>👋 Lever la main</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>we_ctrl_hand</WidgetId>
          <Name>Lever la main</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_9</WidgetId>
          <Name>💬 Chat</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>we_ctrl_chat</WidgetId>
          <Name>Chat</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_7</WidgetId>
          <Name>👫 Participants</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>we_ctrl_participants</WidgetId>
          <Name>Participants</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>we_ctrl_enregistrement</WidgetId>
          <Name>Accepter l\'enregistrement</Name>
          <Type>Button</Type>
          <Options>size=3</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>we_ctrl_menu</WidgetId>
          <Name>Menu [#]</Name>
          <Type>Button</Type>
          <Options>size=2</Options>
        </Widget>
      </Row>
      <Options>hideRowNames=1</Options>
    </Page>
  </Panel>
</Extensions>`;
}

/********************************************************
 * SECTION 3: RUNTIME STATE
 ********************************************************/

var state = {
  isActiveCall: false,
  activeCallId: null,
  activeCallUri: null,
  cachedConferenceUris: [],
  uiSnapshot: null,
  pendingInput: null,
  suppressWidgetAction: false,
  dialInitiated: false,
  lastMicMuteStatus: null,
  lastVideoMuteStatus: null,
};

/********************************************************
 * SECTION 4: PURE HELPERS
 ********************************************************/

function log() {
  var args = Array.prototype.slice.call(arguments);
  args.unshift('[' + SERVICE.name + ']');
  console.log.apply(console, args);
}

function delay(ms) {
  return new Promise(function (res) { setTimeout(res, ms); });
}

function safeString(value) {
  return (value === undefined || value === null) ? '' : String(value);
}

function stripSipProto(raw) {
  return safeString(raw).toLowerCase().trim().replace(/^sips?:/, '');
}

function isSparkUri(uri) {
  var u = safeString(uri).toLowerCase().trim();
  return u.startsWith('spark:');
}

function normalizeHostValue(raw) {
  return stripSipProto(raw).replace(/^@/, '');
}

function getConfiguredHost() {
  return normalizeHostValue(SERVICE.matching.allowedHost || SERVICE.matching.postfix);
}

function extractUriHost(uri) {
  var u = stripSipProto(uri);
  if (!u) return '';
  var at = u.lastIndexOf('@');
  if (at < 0) return '';
  return u.slice(at + 1);
}

function getCallIdentity(raw) {
  var uri = safeString(raw && (raw.RemoteURI || raw.RemoteNumber || raw.CallbackNumber)).trim();
  var status = safeString(raw && raw.Status).toLowerCase();
  var callId = safeString(raw && (raw.CallId || raw.id)).trim();
  var normalizedUri = stripSipProto(uri);
  return {
    callId: callId || null,
    uri: uri,
    normalizedUri: normalizedUri || null,
    status: status,
    isConnected: !!status && status !== 'disconnected' && status !== 'idle',
    isDirect: isServiceCallUri(uri),
    isSparkLeg: isSparkUri(uri),
  };
}

function matchesStoredOwnedCall(callIdentity) {
  if (!callIdentity) return false;
  if (state.activeCallId && callIdentity.callId && state.activeCallId === callIdentity.callId) return true;
  if (state.activeCallUri && callIdentity.normalizedUri && state.activeCallUri === callIdentity.normalizedUri) return true;
  return false;
}

function rememberOwnedCallHint(raw) {
  var uri = safeString(raw && (raw.Uri || raw.RemoteURI || raw.RemoteNumber || raw.CallbackNumber)).trim();
  var callId = safeString(raw && (raw.CallId || raw.id)).trim();
  var normalizedUri = stripSipProto(uri);
  if (callId) state.activeCallId = callId;
  if (normalizedUri) state.activeCallUri = normalizedUri;
}

function syncOwnedCallState(callIdentity) {
  var nextId = callIdentity && callIdentity.callId ? callIdentity.callId : null;
  var nextUri = callIdentity && callIdentity.normalizedUri ? callIdentity.normalizedUri : null;
  var changed = state.activeCallId !== nextId || state.activeCallUri !== nextUri || state.isActiveCall !== !!callIdentity;
  state.isActiveCall = !!callIdentity;
  state.activeCallId = nextId;
  state.activeCallUri = nextUri;
  if (changed) { state.lastMicMuteStatus = null; state.lastVideoMuteStatus = null; }
  return callIdentity;
}

function getCodecVersion() {
  return xapi.Status.SystemUnit.Software.Version.get().then(function (v) { return v; }).catch(function () { return null; });
}

function getMajorVersion(version) {
  if (!version) return null;
  var v = String(version).trim().toLowerCase();
  if (v.startsWith('ce')) { var major = parseInt(v.slice(2).split('.')[0], 10); return Number.isFinite(major) ? major : null; }
  var m = v.match(/(\d+)(?:\.\d+)?/);
  if (!m) return null;
  var major2 = parseInt(m[1], 10);
  return Number.isFinite(major2) ? major2 : null;
}

/********************************************************
 * SECTION 5: CALL MATCHING
 ********************************************************/

function isServiceCallUri(uri) {
  var raw = safeString(uri);
  var u = stripSipProto(raw);
  if (!u) return false;
  var starts = u.startsWith(SERVICE.matching.prefix);
  var ends = u.endsWith(SERVICE.matching.postfix);
  return starts && ends;
}

function isServiceParticipantUri(uri) {
  var u = stripSipProto(uri);
  var host = extractUriHost(uri);
  if (!u) return false;
  if (!u.startsWith(SERVICE.matching.prefix)) return false;
  if (!host) return false;
  return host === getConfiguredHost();
}

function hasServiceParticipantInConference() {
  return state.cachedConferenceUris.some(isServiceParticipantUri);
}

function hasMuteOwnershipHint() {
  if (state.isActiveCall || state.activeCallId || state.activeCallUri) return true;
  if (SERVICE.matching.sparkFallback && hasServiceParticipantInConference()) return true;
  return false;
}

function getCalls() {
  return xapi.Status.Call.get().then(function (raw) {
    if (!raw) return [];
    var calls = Array.isArray(raw) ? raw : [raw];
    return calls;
  }).catch(function (e) { log('getCalls() error:', e); return []; });
}

function findOwnedServiceCall(calls) {
  var connectedCalls = [];
  var confHit = SERVICE.matching.sparkFallback && hasServiceParticipantInConference();
  var i;
  for (i = 0; i < calls.length; i++) {
    var callIdentity = getCallIdentity(calls[i]);
    if (callIdentity.isConnected) connectedCalls.push(callIdentity);
  }
  if (state.activeCallId || state.activeCallUri) {
    for (i = 0; i < connectedCalls.length; i++) {
      var current = connectedCalls[i];
      if (!matchesStoredOwnedCall(current)) continue;
      if (current.isDirect) return current;
      if (SERVICE.matching.sparkFallback && (current.isSparkLeg || confHit || state.isActiveCall)) return current;
    }
  }
  for (i = 0; i < connectedCalls.length; i++) { if (connectedCalls[i].isDirect) return connectedCalls[i]; }
  if (SERVICE.matching.sparkFallback && confHit) {
    for (i = 0; i < connectedCalls.length; i++) { if (connectedCalls[i].isSparkLeg) return connectedCalls[i]; }
  }
  return null;
}

function resolveOwnedServiceCall() {
  return getCalls().then(function (calls) {
    var ownedCall = findOwnedServiceCall(calls);
    syncOwnedCallState(ownedCall);
    return ownedCall;
  }).catch(function (e) { log('resolveOwnedServiceCall() error:', e); return null; });
}

/********************************************************
 * SECTION 6: UI HELPERS
 ********************************************************/

function setWidgetValueSilently(widgetId, value) {
  state.suppressWidgetAction = true;
  return xapi.Command.UserInterface.Extensions.Widget.SetValue({ WidgetId: widgetId, Value: value }).catch(function () {}).then(function () { state.suppressWidgetAction = false; });
}

function rememberConferenceUri(uri) {
  var u = safeString(uri).toLowerCase();
  if (!u) return;
  if (state.cachedConferenceUris.indexOf(u) === -1) state.cachedConferenceUris.push(u);
}

function clearConferenceUris() { state.cachedConferenceUris = []; }

function setPanelsVisibility(ids, visibility) {
  return Promise.all(ids.map(function (id) {
    return xapi.Command.UserInterface.Extensions.Panel.Update({ PanelId: id, Visibility: visibility }).catch(function () {});
  }));
}

var panelVisibilityQueue = Promise.resolve();
function queuePanelVisibilityWork(workFn) {
  panelVisibilityQueue = panelVisibilityQueue.then(function () { return workFn(); }).catch(function (e) { log('Panel visibility queue error:', e); });
  return panelVisibilityQueue;
}

function savePanelXml(panelId, xml) {
  return xapi.command('UserInterface Extensions Panel Save', { PanelId: panelId }, xml).catch(function (err) { log('Failed to save panel:', panelId, err); });
}

function updatePanelVisibilitySafe(panelId, visibility) {
  if (!panelId) return Promise.resolve();
  return xapi.Command.UserInterface.Extensions.Panel.Update({ PanelId: panelId, Visibility: visibility }).catch(function (err) { log('Panel visibility update failed:', panelId, visibility, err); });
}

function normalizePanelListResponse(raw) {
  var extensions = raw && raw.Extensions ? raw.Extensions : raw;
  var panels = extensions && extensions.Panel ? extensions.Panel : [];
  if (!panels) return [];
  return Array.isArray(panels) ? panels : [panels];
}

function listExtensionPanels() {
  return xapi.Command.UserInterface.Extensions.List().then(function (raw) { return normalizePanelListResponse(raw); }).catch(function () { return []; });
}

function isLocalPanel(panel) { return safeString(panel && panel.Origin).toLowerCase() === 'local'; }

function isDynamicControlsPanel(panel) {
  var panelId = safeString(panel && panel.PanelId);
  var type = safeString(panel && panel.Type).toLowerCase();
  var location = safeString(panel && panel.Location).toLowerCase();
  if (!panelId) return false;
  if (panelId === SERVICE.panels.controls) return true;
  if (type === 'incall') return true;
  if (location === 'callcontrols') return true;
  if (/_controls$/i.test(panelId)) return true;
  return false;
}

function listManagedControlsPanelIds() {
  return listExtensionPanels().then(function (panels) {
    var ids = [];
    for (var i = 0; i < panels.length; i++) {
      var panel = panels[i];
      var panelId = safeString(panel && panel.PanelId);
      if (!panelId) continue;
      if (!isLocalPanel(panel)) continue;
      if (!isDynamicControlsPanel(panel)) continue;
      ids.push(panelId);
    }
    if (ids.indexOf(SERVICE.panels.controls) === -1) ids.push(SERVICE.panels.controls);
    return ids;
  });
}

function hideAllControlsPanelsExcept(keepPanelId) {
  return listManagedControlsPanelIds().then(function (ids) {
    var updates = [];
    for (var i = 0; i < ids.length; i++) {
      if (keepPanelId && ids[i] === keepPanelId) continue;
      updates.push(updatePanelVisibilitySafe(ids[i], 'Hidden'));
    }
    return Promise.all(updates);
  });
}

function initializePanelVisibility() {
  return queuePanelVisibilityWork(function () {
    return hideAllControlsPanelsExcept(null)
      .then(function () { return updatePanelVisibilitySafe(SERVICE.panels.controls, 'Hidden'); })
      .then(function () { return updatePanelVisibilitySafe(SERVICE.panels.home, 'Auto'); });
  });
}

function showOnlyOwnedControlsPanel() {
  return queuePanelVisibilityWork(function () {
    return hideAllControlsPanelsExcept(SERVICE.panels.controls)
      .then(function () { return updatePanelVisibilitySafe(SERVICE.panels.controls, 'Auto'); })
      .then(function () { return updatePanelVisibilitySafe(SERVICE.panels.home, 'Auto'); });
  });
}

function resetToggleWidgets() {
  return Promise.all(TOGGLE_WIDGET_IDS.map(function (id) {
    return xapi.Command.UserInterface.Extensions.Widget.SetValue({ WidgetId: id, Value: 'off' }).catch(function () {});
  }));
}

function snapshotUIFeatures() {
  return xapi.Status.UserInterface.Features.get().then(function (config) {
    state.uiSnapshot = config;
    var call = config && config.Call;
    if (call && ('Breakouts' in call)) delete call.Breakouts;
    if (config && ('Files' in config)) delete config.Files;
    if (config && ('Whiteboard' in config)) delete config.Whiteboard;
  }).catch(function () { state.uiSnapshot = null; });
}

function applyServiceUI() {
  if (!SERVICE.features.lockdownUI) return Promise.resolve();
  var settings = [
    ['UserInterface Features Call Keypad', 'Auto'],
    ['UserInterface Features Call LayoutControls', 'Hidden'],
    ['UserInterface Features Call MidCallControls', 'Hidden'],
    ['UserInterface Features Call MusicMode', 'Hidden'],
    ['UserInterface Features Call ParticipantList', 'Hidden'],
    ['UserInterface Features Call SelfviewControls', 'Hidden'],
    ['UserInterface Features Call VideoMute', 'Auto'],
  ];
  return settings.reduce(function (chain, pair) {
    return chain.then(function () { return xapi.config.set(pair[0], pair[1]).catch(function () {}); });
  }, Promise.resolve());
}

function enforceExclusiveToggles(widgetId, value) {
  if (value !== 'on') return Promise.resolve();
  var exclusives = SERVICE.features.exclusiveToggles;
  if (!exclusives) return Promise.resolve();
  var otherId = exclusives[widgetId];
  if (!otherId) return Promise.resolve();
  state.suppressWidgetAction = true;
  return xapi.Command.UserInterface.Extensions.Widget.SetValue({ WidgetId: otherId, Value: 'off' }).catch(function () {}).then(function () { state.suppressWidgetAction = false; });
}

function ensureHttpHostAllowed() {
  if (!SERVICE.features.httpHostAllowed) return Promise.resolve();
  var host = SERVICE.matching.allowedHost;
  return xapi.Command.HttpClient.Allow.Hostname.List().then(function (list) {
    var found = false;
    var hostNames = list && list.HostName;
    if (hostNames && hostNames.length > 0) {
      for (var i = 0; i < hostNames.length; i++) {
        if (hostNames[i].Expression === host) { found = true; break; }
      }
    }
    if (!found) return xapi.Command.HttpClient.Allow.Hostname.Add({ Expression: host });
  }).catch(function () { return xapi.Command.HttpClient.Allow.Hostname.Add({ Expression: host }).catch(function () {}); });
}

/********************************************************
 * SECTION 7: DTMF HELPERS
 ********************************************************/

function sendChatSequence(ownedCall) {
  var participantsCode = SERVICE.dtmf.participants;
  var chatCode = SERVICE.dtmf.conversation;
  if (!chatCode) return Promise.resolve();
  if (state.participantsOpen) {
    state.chatOpen = true;
    return safeDTMF(chatCode, ownedCall);
  }
  return safeDTMF(participantsCode, ownedCall).then(function () {
    state.participantsOpen = true;
    return setWidgetValueSilently('we_ctrl_participants', 'on');
  }).then(function () { return delay(250); }).then(function () {
    state.chatOpen = true;
    return safeDTMF(chatCode, ownedCall);
  });
}

function safeDTMF(digits, ownedCall) {
  var resolver = ownedCall ? Promise.resolve(ownedCall) : resolveOwnedServiceCall();
  return resolver.then(function (resolvedCall) {
    if (!resolvedCall) { log('DTMF NOT sent (no owned service call):', digits); return; }
    var params;
    if (resolvedCall.callId) { params = { CallId: resolvedCall.callId, DTMFString: String(digits) }; }
    else { params = { DTMFString: String(digits), Feedback: 'Silent' }; }
    return xapi.Command.Call.DTMFSend(params);
  }).catch(function (e) { log('DTMF send failed:', digits, e); });
}

function resolveWidgetDTMF(widgetId) {
  var cfg = SERVICE.widgets[widgetId];
  if (!cfg) return null;
  return SERVICE.dtmf[cfg.dtmf] || null;
}

/********************************************************
 * SECTION 8: INPUT / DIAL FLOW
 ********************************************************/

function dial(number) {
  state.dialInitiated = true;
  return xapi.Command.Dial({ Number: number, Protocol: 'SIP', CallType: 'Video' }).catch(function (e) { log('Dial failed:', e); });
}

function showMeetingPrompt(text) {
  var promptText = text || SERVICE.input.defaultPrompt;
  return xapi.Command.UserInterface.Message.TextInput.Display({
    InputType: SERVICE.input.inputType,
    Placeholder: SERVICE.input.placeholder,
    Title: SERVICE.input.title,
    Text: promptText,
    SubmitText: SERVICE.input.submitText,
    FeedbackId: SERVICE.input.feedbackId,
  }).catch(function () {});
}

function isAsciiNoAccents(str) {
  return /^[A-Za-z0-9._-]+$/.test(str);
}

function hasAtLeastThreeDigits(str) {
  var m = str.match(/\d/g);
  return (m && m.length || 0) >= 3;
}

function validateMeetingInput(meetingID) {
  if (meetingID === '0') return { valid: true, dialString: SERVICE.matching.prefix + '.' + meetingID + SERVICE.matching.postfix };
  var isAllDigits = /^\d{10}$/.test(meetingID);
  var looksValidName =
    meetingID.length >= 10 &&
    isAsciiNoAccents(meetingID) &&
    hasAtLeastThreeDigits(meetingID);

  if (isAllDigits || looksValidName) {
    return {
      valid: true,
      dialString: SERVICE.matching.prefix + '.' + meetingID + SERVICE.matching.postfix,
    };
  }

  return {
    valid: false,
    errorTitle: 'Le numéro de conférence est invalide.',
    errorText: 'Saisissez un code de 10 chiffres.',
  };
}

function handleMeetingSubmit(value) {
  var meetingID = (value && value.Text ? String(value.Text).trim() : '');
  if (!meetingID) return Promise.resolve();
  var result = validateMeetingInput(meetingID);
  if (!result.valid) {
    return xapi.Command.UserInterface.Message.Alert.Display({ Title: result.errorTitle, Text: result.errorText, Duration: 10 }).catch(function () {});
  }
  return dial(result.dialString);
}

/********************************************************
 * SECTION 9: EVENT HANDLERS
 ********************************************************/

function onServiceCallStarted(callIdentity) {
  syncOwnedCallState(callIdentity);
  return snapshotUIFeatures()
    .then(function () { return applyServiceUI(); })
    .then(function () { return xapi.Command.Video.Selfview.Set({ Mode: 'Off' }).catch(function () {}); })
    .then(function () { return showOnlyOwnedControlsPanel(); })
    .then(function () { if (SERVICE.features.autoMuteOnJoin) return xapi.Command.Audio.Microphones.Mute().catch(function () {}); });
}

function clearServiceStateAndHide() {
  syncOwnedCallState(null);
  state.dialInitiated = false;
  state.participantsOpen = false;
  state.chatOpen = false;
  return queuePanelVisibilityWork(function () { return updatePanelVisibilitySafe(SERVICE.panels.controls, 'Hidden'); })
    .then(function () { clearConferenceUris(); })
    .then(function () { return resetToggleWidgets(); });
}

function ensureOwnedCallUI(ownedCall, wasActive) {
  if (!ownedCall) return clearServiceStateAndHide();
  if (wasActive) { syncOwnedCallState(ownedCall); return showOnlyOwnedControlsPanel(); }
  return onServiceCallStarted(ownedCall);
}

function handleCallSuccessful(ev) {
  var callIdentity = getCallIdentity(ev);
  var wasActive = state.isActiveCall;
  if (callIdentity.isDirect) return ensureOwnedCallUI(callIdentity, wasActive);
  return resolveOwnedServiceCall().then(function (ownedCall) { return ensureOwnedCallUI(ownedCall, wasActive); });
}

function handleCallDisconnect(ev) {
  var disconnectedCall = getCallIdentity(ev);
  var wasActive = state.isActiveCall;
  if (matchesStoredOwnedCall(disconnectedCall)) syncOwnedCallState(null);
  return resolveOwnedServiceCall().then(function (ownedCall) { return ensureOwnedCallUI(ownedCall, wasActive); });
}

function handleParticipantUpdated(ev) {
  var uri = (ev && ev.Uri) ? ev.Uri : '';
  var wasActive = state.isActiveCall;
  rememberConferenceUri(uri);
  if (!isServiceParticipantUri(uri)) return Promise.resolve();
  rememberOwnedCallHint(ev);
  return resolveOwnedServiceCall().then(function (ownedCall) {
    if (!ownedCall) return Promise.resolve();
    return ensureOwnedCallUI(ownedCall, wasActive);
  });
}

function handleWidgetAction(event) {
  var WidgetId = event.WidgetId;
  var Type = event.Type;
  var Value = event.Value;
  if (state.suppressWidgetAction) return Promise.resolve();
  var cfg = SERVICE.widgets[WidgetId];
  if (!cfg) return Promise.resolve();
  if (cfg.kind === 'button' && Type !== 'clicked') return Promise.resolve();
  if (cfg.kind === 'toggle' && Type !== 'changed') return Promise.resolve();
  if (cfg.kind === 'toggle') {
    return resolveOwnedServiceCall().then(function (ownedCall) {
      if (!ownedCall) {
        state.participantsOpen = false; state.chatOpen = false;
        return xapi.Command.UserInterface.Extensions.Widget.SetValue({ WidgetId: WidgetId, Value: 'off' }).catch(function () {});
      }
      return enforceExclusiveToggles(WidgetId, Value).then(function () {
        if (WidgetId === 'we_ctrl_participants') {
          if (Value === 'on') { state.participantsOpen = true; return safeDTMF(SERVICE.dtmf.participants, ownedCall); }
          state.participantsOpen = false;
          var closeChatUi = Promise.resolve();
          if (state.chatOpen) { state.chatOpen = false; closeChatUi = setWidgetValueSilently('we_ctrl_chat', 'off'); }
          return closeChatUi.then(function () { return safeDTMF(SERVICE.dtmf.participants, ownedCall); });
        }
        if (WidgetId === 'we_ctrl_chat') {
          if (Value === 'on') return sendChatSequence(ownedCall);
          state.chatOpen = false;
          return safeDTMF(SERVICE.dtmf.conversation, ownedCall);
        }
        var dtmfCode = resolveWidgetDTMF(WidgetId);
        if (dtmfCode) return safeDTMF(dtmfCode, ownedCall);
      });
    });
  }
  var dtmfCode = resolveWidgetDTMF(WidgetId);
  if (dtmfCode) return safeDTMF(dtmfCode);
  return Promise.resolve();
}

function handlePanelClicked(ev) { if (ev && ev.PanelId === SERVICE.panels.home) showMeetingPrompt(); }

function handleTextInputResponse(ev) {
  if (ev && ev.FeedbackId === SERVICE.input.feedbackId) return handleMeetingSubmit(ev);
  return Promise.resolve();
}

function normalizeMuteStatus(ev) {
  return (ev && ev.Status != null) ? ev.Status : (ev && ev.Mute != null) ? ev.Mute : ev;
}

function handleVideoMuteChange(ev) {
  var status = normalizeMuteStatus(ev);
  if (!SERVICE.features.videoMuteDtmf) return Promise.resolve();
  if (status !== 'On' && status !== 'Off') return Promise.resolve();
  if (!hasMuteOwnershipHint()) return Promise.resolve();
  return resolveOwnedServiceCall().then(function (ownedCall) {
    if (!ownedCall) return Promise.resolve();
    if (state.lastVideoMuteStatus === status) return Promise.resolve();
    state.lastVideoMuteStatus = status;
    return safeDTMF(SERVICE.features.videoMuteDtmf, ownedCall);
  });
}

function handleMicMuteChange(ev) {
  var status = normalizeMuteStatus(ev);
  if (!SERVICE.features.micMuteDtmf) return Promise.resolve();
  if (status !== 'On' && status !== 'Off') return Promise.resolve();
  if (!hasMuteOwnershipHint()) return Promise.resolve();
  return resolveOwnedServiceCall().then(function (ownedCall) {
    if (!ownedCall) return Promise.resolve();
    if (state.lastMicMuteStatus === status) return Promise.resolve();
    state.lastMicMuteStatus = status;
    return safeDTMF(SERVICE.features.micMuteDtmf, ownedCall);
  });
}

/********************************************************
 * SECTION 10: BOOT
 ********************************************************/

function injectPanels() {
  return savePanelXml(SERVICE.panels.home, HOME_PANEL_XML).then(function () {
    if (!SERVICE.features.codecVersionCheck) {
      return savePanelXml(SERVICE.panels.controls, buildControlsPanelXml('<Location>CallControls</Location>'));
    }
    return getCodecVersion().then(function (version) {
      var major = getMajorVersion(version);
      var placementLine = (major === 9) ? '<Type>InCall</Type>' : '<Location>CallControls</Location>';
      return savePanelXml(SERVICE.panels.controls, buildControlsPanelXml(placementLine));
    });
  });
}

function wireEvents() {
  xapi.Command.UserInterface.Extensions.Panel.Update({ PanelId: SERVICE.panels.home, Visibility: 'Auto' }).catch(function () {});
  xapi.Command.UserInterface.Extensions.Panel.Update({ PanelId: SERVICE.panels.controls, Visibility: 'Hidden' }).catch(function () {});
  xapi.Event.UserInterface.Extensions.Panel.Clicked.on(function (ev) { handlePanelClicked(ev); });
  xapi.Event.UserInterface.Message.TextInput.Response.on(function (ev) { handleTextInputResponse(ev); });
  if (SERVICE.matching.sparkFallback) {
    xapi.Event.Conference.ParticipantList.ParticipantUpdated.on(function (ev) {
      handleParticipantUpdated(ev).catch(function (e) { log('ParticipantUpdated handler error:', e); });
    });
  }
  xapi.Event.CallSuccessful.on(function (ev) { handleCallSuccessful(ev).catch(function (e) { log('CallSuccessful handler error:', e); }); });
  xapi.Event.CallDisconnect.on(function (ev) { handleCallDisconnect(ev).catch(function (e) { log('CallDisconnect handler error:', e); }); });
  if (SERVICE.features.videoMuteDtmf) {
    xapi.Status.Video.Input.MainVideoMute.on(function (ev) { handleVideoMuteChange(ev).catch(function (e) { log('Video mute handler error:', e); }); });
  }
  if (SERVICE.features.micMuteDtmf) {
    xapi.Status.Audio.Microphones.Mute.on(function (ev) { handleMicMuteChange(ev).catch(function (e) { log('Mic mute handler error:', e); }); });
  }
  xapi.Event.UserInterface.Extensions.Widget.Action.on(function (event) { handleWidgetAction(event); });
}

(function boot() {
  injectPanels()
    .then(function () { return initializePanelVisibility(); })
    .then(function () { return ensureHttpHostAllowed(); })
    .then(function () { wireEvents(); return delay(100); })
    .then(function () {
      var wasActive = state.isActiveCall;
      return resolveOwnedServiceCall().then(function (ownedCall) {
        if (!ownedCall) return Promise.resolve();
        return ensureOwnedCallUI(ownedCall, wasActive);
      });
    })
    .catch(function (e) { log('Boot error:', e); });
})();