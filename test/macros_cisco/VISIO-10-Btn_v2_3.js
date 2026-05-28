import xapi from 'xapi'; 

/********************************************************
 * SECTION 1: METADATA
 ********************************************************/

const METADATA = {
  name: 'VISIO',
  version: 'VISIO-10-Btn_v2_3',
  description: 'Visio conferencing macro',
};

/********************************************************
 * SECTION 2: CONFIG (SERVICE)
 ********************************************************/

const SERVICE = {
  name: METADATA.name,
  version: METADATA.version,

  panels: {
    home: 'visio_button',
    controls: 'visio_controls',
    home_icon: 'visio24be29b93386cdf35e3d1febae36616c',
    controls_icon:'visioctrl86e87c870ec38524e05a82a3535c13a5'
  },

  matching: {
    prefix: '3',
    postfix: '@rdv.visio.renater.fr',
    allowedHost: 'rdv.visio.renater.fr',
    sparkFallback: true,
  },

  features: {
    autoMuteOnJoin: false,
    lockdownUI: true,
    dynamicPanel: false,
    exclusiveToggles: {
      visio_ctrl_chat: 'visio_ctrl_participants',
      visio_ctrl_participants: 'visio_ctrl_chat',
    },
    codecVersionCheck: true,
    micMuteDtmf: '1',
    videoMuteDtmf: '2',
    httpHostAllowed: true,
  },

  dtmf: {
    audio: '1',
    video: '2',
    conversation: '3',
    hand: '4',
    participants: '5',
    full_screen: '6',
    enregistrement: '7',
    emote_thumb: '01',
    emote_heart: '02',
    emote_applause: '03',
    emote_laugh: '04',
    menu: '#',
  },

  widgets: {
    visio_ctrl_hand:           { kind: 'toggle', dtmf: 'hand' },
    visio_ctrl_chat:           { kind: 'toggle', dtmf: 'conversation' },
    visio_ctrl_participants:   { kind: 'toggle', dtmf: 'participants' },
    visio_ctrl_full_screen:    { kind: 'toggle', dtmf: 'full_screen' },
    visio_ctrl_enregistrement: { kind: 'toggle', dtmf: 'enregistrement' },
    visio_ctrl_emote_thumb:    { kind: 'button', dtmf: 'emote_thumb' },
    visio_ctrl_emote_heart:    { kind: 'button', dtmf: 'emote_heart' },
    visio_ctrl_emote_applause: { kind: 'button', dtmf: 'emote_applause' },
    visio_ctrl_emote_laugh:    { kind: 'button', dtmf: 'emote_laugh' },
    visio_ctrl_menu:           { kind: 'button', dtmf: 'menu' },
  },

  input: {
    mode: 'single',
    feedbackId: 'VISIO_MEETING',
    inputType: 'SingleLine',
    placeholder: 'Saisissez un code à 10 chiffres.',
    title: "Visio",
    defaultPrompt: "Saisissez l'identifiant de la conférence que vous souhaitez créer ou rejoindre:",
    submitText: 'Appeler',
  },
};

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
    <Name>Visio</Name>
    <ActivityType>Custom</ActivityType>
    <CustomIcon>
      <Content>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</Content>
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
    <Name>Interactions Visio</Name>
    <ActivityType>Custom</ActivityType>
    <CustomIcon>
      <Content>iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAAFmklEQVR42u1aXWgcVRQ+Z2YzU9zatFsT/ImCD+YhDxYhIoggCj70xz74IKhv+qBPxQdBRDB5FUSw+AM+aJ/zYBVqFVrJk7TqkkSIFhZLCHZlN2k2u9mdnbl/c3zInTCdTrK7s5NkU+aDZf/u3Lnfvd85595zBiBDhgwZMmTIkGGPgGl2RkQIAGbwNdS/QkS6Z2aNiJCIzA5tTD0h+4pcCmRNRFQAoIrF4vDExMRZ0zSfBYDjRFQnoutra2s/IOJapP2BW1WDiAwAgJmZGctxnHNCiGWKgRDiv1ar9X6xWLwveu1Bke+WMmq12lnO+UKInyQioZSSRCT0KyD+d7PZfHXQZL4tZmdnt4hWKpUnGWPfhxdSKeVTPPwwccbYz/V6fTJEPNevA9WqyYXesV87BQCAcrn8gOu6n0gpPT1+pV/dQGkFkJRSMsY+X15efjh8n6Rkd8P7Go7jvC2E+Dci3ySQIZlXHcd5d2Zmxkoi88C8yuXyY67rfsY5/6ndbn90+fJlW48fuyYbfG42my8KIa6F5atlSh0kvG0b3/cpLHPO+Xyr1ToVd/9OZDc2Np4XQlTC/Xue90XXqiEiRERYWlo65Hnel5GV8Sld3GHfnuddKJVKR3YiHXaczWbzDSklC+ZNKSU2hSPWFhcXD3ecPN2ZUSqVbMbY1YCoUkp1OXiSUq56nvetlLIc/r1b+2aMXa9Wq4e1A7pjsFNTU1shrd1ufxDqX4XvxTlvLCwsjHZD2AQAcBzn48Cp9mqbzWbzNQCARqNxKkSmWzAiona7/XVUkiHnhIyxr7ZR3Rbhubm5kShhIzp7iKhu3779iG3b5wDAB4ChXvfmRFQmopzjONUEe/YhAFC2bb+5srIyjogqWGlE9IvF4jBj7JJlWe8AgNQT0nX/dxCenp42AADy+fxLpmke0oR7jmeIOISIEhGTbF0RAMgwDDOfz58Ob4Gr1eqDJ06cmLUs6xQASADIBeGy3730uD7tJI5okfdEME3zidAkkuu63+RyuacAgAOAlaTP2IBtGEY+7aNjosEZxmFNljcajXHbtk8CgE9EVuI+434UQlgwAOCcb43D9/1HA/n2KuOOku6wVSNt23Hw9f+k+yEAUJFkQNyk4za+IM5M9vw8HM5q3GV2gdPSkszt0HbgEwAEAKiU2vB9/1fajBMUs8IG57wKACClXBNC/GgYBvm+jzFbVzRN8xnTNAsdVLA/hIkI19fXXxkZGfmlmwvGxsZKAHBmpzarq6uThULhmmEY5l6QPhhZh31aYUREOHbs2Hec8x0l3Wq1PiwUCn/eunVrfHR09NNOkta2PnCSRr0ZOGKa5smdGlqWdR4AIJfLHR8aGjqtr9vTlHGaXrpTWDKISOjYKfsJS3Fbzl0hjIh+wrCEYQK4GUgTO6PNML6FWhqkY52WbdtsEByMZVk8yGzcvHlzUUr5lx6zTJWwlLKd1s6mH/i+3wo2NJOTk6Ldbr+llNrQylSpEQaAUp9OBNNwREKIf/RHRUTG8PDwb7Va7QUp5bI2FdkX4enpaV9nO64opTz9PyWwPaFzw0mkRwCAvu8r13UvBYuNiD4RmaOjo3OVSuU5zvkfeqVlXzJKI8VTr9df340UT/j7wsJCnjF2MSaL2nNOK5Uknuu6F5Im8YQQ12/cuHF/XBIveprzPO98aLJl0I8Qoj4/P3+0q5TvoKdpwwujs5fv3SUTxq70VJXYj0R8o9E43WMifqsy0mg0zgghfpdSVhljV9fX1x8PT0riUouUcqBKLVE7X1paOppGjWnXimkrKysPxQ28nzESEU5NTfV/EoyWSznnF8Or1mO59OlIjSiVw0Pq9eZoQdxxnJfv2YJ4NDQcxEceMCX7VgAAOz3UMjY2drAfatnBm287MYMg3+zBtAwZMmTIkCFDht3C/4cArvcfVg/DAAAAAElFTkSuQmCC</Content>
      <Id>${SERVICE.panels.controls_icon}</Id>
    </CustomIcon>
    <Page>
      <Name>Visio</Name>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_6</WidgetId>
          <Name>👋 Lever la main</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>visio_ctrl_hand</WidgetId>
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
          <WidgetId>visio_ctrl_chat</WidgetId>
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
          <WidgetId>visio_ctrl_participants</WidgetId>
          <Name>Participants</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>visio_ctrl_emote_thumb</WidgetId>
          <Name>👍</Name>
          <Type>Button</Type>
          <Options>size=1</Options>
        </Widget>
        <Widget>
          <WidgetId>visio_ctrl_emote_heart</WidgetId>
          <Name>💕</Name>
          <Type>Button</Type>
          <Options>size=1</Options>
        </Widget>
        <Widget>
          <WidgetId>visio_ctrl_emote_applause</WidgetId>
          <Name>👏</Name>
          <Type>Button</Type>
          <Options>size=1</Options>
        </Widget>
        <Widget>
          <WidgetId>visio_ctrl_emote_laugh</WidgetId>
          <Name>😆</Name>
          <Type>Button</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>visio_ctrl_menu</WidgetId>
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
  if (state.activeCallId && callIdentity.callId && state.activeCallId === callIdentity.callId) {
    return true;
  }
  if (state.activeCallUri && callIdentity.normalizedUri && state.activeCallUri === callIdentity.normalizedUri) {
    return true;
  }
  return false;
}

function rememberOwnedCallHint(raw) {
  var uri = safeString(raw && (raw.Uri || raw.RemoteURI || raw.RemoteNumber || raw.CallbackNumber)).trim();
  var callId = safeString(raw && (raw.CallId || raw.id)).trim();
  var normalizedUri = stripSipProto(uri);

  if (callId) {
    state.activeCallId = callId;
  }
  if (normalizedUri) {
    state.activeCallUri = normalizedUri;
  }
}

function syncOwnedCallState(callIdentity) {
  var nextId = callIdentity && callIdentity.callId ? callIdentity.callId : null;
  var nextUri = callIdentity && callIdentity.normalizedUri ? callIdentity.normalizedUri : null;
  var changed =
    state.activeCallId !== nextId ||
    state.activeCallUri !== nextUri ||
    state.isActiveCall !== !!callIdentity;

  state.isActiveCall = !!callIdentity;
  state.activeCallId = nextId;
  state.activeCallUri = nextUri;

  if (changed) {
    state.lastMicMuteStatus = null;
    state.lastVideoMuteStatus = null;
  }

  return callIdentity;
}

function getCodecVersion() {
  return xapi.Status.SystemUnit.Software.Version.get()
    .then(function (v) { return v; })
    .catch(function () { return null; });
}

function getMajorVersion(version) {
  if (!version) return null;
  var v = String(version).trim().toLowerCase();
  if (v.startsWith('ce')) {
    var major = parseInt(v.slice(2).split('.')[0], 10);
    return Number.isFinite(major) ? major : null;
  }
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

  if (!u) {
    log('isServiceCallUri: EMPTY/invalid uri', { raw: raw });
    return false;
  }

  var starts = u.startsWith(SERVICE.matching.prefix);
  var ends = u.endsWith(SERVICE.matching.postfix);
  var result = starts && ends;

  var looksRelevant =
    result ||
    starts ||
    ends ||
    u.includes(SERVICE.matching.allowedHost) ||
    raw.toLowerCase().includes(SERVICE.matching.allowedHost);

  if (looksRelevant) {
    log('isServiceCallUri check', {
      raw: raw,
      stripped: u,
      prefix: SERVICE.matching.prefix,
      postfix: SERVICE.matching.postfix,
      startsWithPrefix: starts,
      endsWithPostfix: ends,
      result: result,
    });
  }

  return result;
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
  if (state.isActiveCall || state.activeCallId || state.activeCallUri) {
    return true;
  }
  if (SERVICE.matching.sparkFallback && hasServiceParticipantInConference()) {
    return true;
  }
  return false;
}

function getCalls() {
  return xapi.Status.Call.get()
    .then(function (raw) {
      if (!raw) return [];
      var calls = Array.isArray(raw) ? raw : [raw];
      return calls;
    })
    .catch(function (e) {
      log('getCalls() error:', e);
      return [];
    });
}

function findOwnedServiceCall(calls) {
  var connectedCalls = [];
  var confHit = SERVICE.matching.sparkFallback && hasServiceParticipantInConference();
  var i;

  for (i = 0; i < calls.length; i++) {
    var callIdentity = getCallIdentity(calls[i]);
    if (callIdentity.isConnected) {
      connectedCalls.push(callIdentity);
    }
  }

  if (state.activeCallId || state.activeCallUri) {
    for (i = 0; i < connectedCalls.length; i++) {
      var current = connectedCalls[i];
      if (!matchesStoredOwnedCall(current)) continue;
      if (current.isDirect) {
        return current;
      }
      if (SERVICE.matching.sparkFallback && (current.isSparkLeg || confHit || state.isActiveCall)) {
        return current;
      }
    }
  }

  for (i = 0; i < connectedCalls.length; i++) {
    if (connectedCalls[i].isDirect) {
      return connectedCalls[i];
    }
  }

  if (SERVICE.matching.sparkFallback && confHit) {
    for (i = 0; i < connectedCalls.length; i++) {
      if (connectedCalls[i].isSparkLeg) {
        return connectedCalls[i];
      }
    }
  }

  return null;
}

function resolveOwnedServiceCall() {
  return getCalls().then(function (calls) {
    var ownedCall = findOwnedServiceCall(calls);
    var confHit = SERVICE.matching.sparkFallback && hasServiceParticipantInConference();

    syncOwnedCallState(ownedCall);
    log('resolveOwnedServiceCall:', {
      activeCallId: state.activeCallId,
      activeCallUri: state.activeCallUri,
      confHit: confHit,
      hasOwnedCall: !!ownedCall,
      ownedCall: ownedCall ? {
        callId: ownedCall.callId,
        uri: ownedCall.uri,
        isDirect: ownedCall.isDirect,
        isSparkLeg: ownedCall.isSparkLeg,
      } : null,
    });

    return ownedCall;
  }).catch(function (e) {
    log('resolveOwnedServiceCall() error:', e);
    return null;
  });
}

function hasActiveServiceCall() {
  return resolveOwnedServiceCall().then(function (ownedCall) {
    var result = !!ownedCall;
    log('hasActiveServiceCall: result =', result);
    return result;
  });
}

/********************************************************
 * SECTION 6: UI HELPERS
 ********************************************************/

function rememberConferenceUri(uri) {
  var u = safeString(uri).toLowerCase();
  if (!u) return;
  if (state.cachedConferenceUris.indexOf(u) === -1) {
    state.cachedConferenceUris.push(u);
  }
}

function clearConferenceUris() {
  state.cachedConferenceUris = [];
}

function setPanelsVisibility(ids, visibility) {
  return Promise.all(ids.map(function (id) {
    return xapi.Command.UserInterface.Extensions.Panel.Update({
      PanelId: id,
      Visibility: visibility,
    }).catch(function () {});
  }));
}

function resetToggleWidgets() {
  return Promise.all(
    TOGGLE_WIDGET_IDS.map(function (id) {
      return xapi.Command.UserInterface.Extensions.Widget.SetValue({
        WidgetId: id,
        Value: 'off',
      }).catch(function () {});
    })
  );
}

function snapshotUIFeatures() {
  return xapi.Status.UserInterface.Features.get()
    .then(function (config) {
      state.uiSnapshot = config;
      var call = config && config.Call;
      if (call && ('Breakouts' in call)) delete call.Breakouts;
      if (config && ('Files' in config)) delete config.Files;
      if (config && ('Whiteboard' in config)) delete config.Whiteboard;
    })
    .catch(function () {
      state.uiSnapshot = null;
    });
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
    return chain.then(function () {
      return xapi.config.set(pair[0], pair[1]).catch(function () {});
    });
  }, Promise.resolve());
}

function enforceExclusiveToggles(widgetId, value) {
  if (value !== 'on') return Promise.resolve();
  var exclusives = SERVICE.features.exclusiveToggles;
  if (!exclusives) return Promise.resolve();
  var otherId = exclusives[widgetId];
  if (!otherId) return Promise.resolve();

  state.suppressWidgetAction = true;
  return xapi.Command.UserInterface.Extensions.Widget.SetValue({
    WidgetId: otherId,
    Value: 'off',
  }).catch(function () {}).then(function () {
    state.suppressWidgetAction = false;
  });
}

function ensureHttpHostAllowed() {
  if (!SERVICE.features.httpHostAllowed) return Promise.resolve();
  var host = SERVICE.matching.allowedHost;
  return xapi.Command.HttpClient.Allow.Hostname.List()
    .then(function (list) {
      var found = false;
      var hostNames = list && list.HostName;
      if (hostNames && hostNames.length > 0) {
        for (var i = 0; i < hostNames.length; i++) {
          if (hostNames[i].Expression === host) {
            found = true;
            break;
          }
        }
      }
      if (!found) {
        return xapi.Command.HttpClient.Allow.Hostname.Add({ Expression: host });
      }
    })
    .catch(function () {
      return xapi.Command.HttpClient.Allow.Hostname.Add({ Expression: host }).catch(function () {});
    });
}

/********************************************************
 * SECTION 7: DTMF HELPERS
 ********************************************************/

function safeDTMF(digits, ownedCall) {
  var resolver = ownedCall ? Promise.resolve(ownedCall) : resolveOwnedServiceCall();
  return resolver.then(function (resolvedCall) {
    if (!resolvedCall) {
      log('DTMF NOT sent (no owned service call):', digits);
      return;
    }

    var params;
    if (resolvedCall.callId) {
      params = {
        CallId: resolvedCall.callId,
        DTMFString: String(digits),
      };
      log('Sending DTMF:', digits, 'on CallId', resolvedCall.callId);
    } else {
      params = {
        DTMFString: String(digits),
        Feedback: 'Silent',
      };
      log('Sending DTMF:', digits);
    }

    return xapi.Command.Call.DTMFSend(params);
  }).catch(function (e) {
    log('DTMF send failed:', digits, e);
  });
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
  return xapi.Command.Dial({
    Number: number,
    Protocol: 'SIP',
    CallType: 'Video',
  }).catch(function (e) {
    log('Dial failed:', e);
  });
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
    return xapi.Command.UserInterface.Message.Alert.Display({
      Title: result.errorTitle,
      Text: result.errorText,
      Duration: 10,
    }).catch(function () {});
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
    .then(function () {
      return xapi.Command.Video.Selfview.Set({ Mode: 'Off' }).catch(function () {});
    })
    .then(function () {
      return setPanelsVisibility([SERVICE.panels.controls], 'Auto');
    })
    .then(function () {
      if (SERVICE.features.autoMuteOnJoin) {
        return xapi.Command.Audio.Microphones.Mute().catch(function () {});
      }
    });
}

function clearServiceStateAndHide() {
  syncOwnedCallState(null);
  state.dialInitiated = false;

  return xapi.Command.UserInterface.Extensions.Panel.Update({
    PanelId: SERVICE.panels.controls,
    Visibility: 'Hidden',
  }).catch(function () {})
    .then(function () { clearConferenceUris(); })
    .then(function () { return resetToggleWidgets(); });
}

function ensureOwnedCallUI(ownedCall, wasActive) {
  if (!ownedCall) {
    return clearServiceStateAndHide();
  }
  if (wasActive) {
    syncOwnedCallState(ownedCall);
    return setPanelsVisibility([SERVICE.panels.controls], 'Auto');
  }
  return onServiceCallStarted(ownedCall);
}

function handleCallSuccessful(ev) {
  var callIdentity = getCallIdentity(ev);
  var wasActive = state.isActiveCall;
  log('CallSuccessful', {
    RemoteURI: callIdentity.uri,
    normalized: callIdentity.normalizedUri,
    CallId: callIdentity.callId,
    isServiceCallUri: callIdentity.isDirect,
  });

  if (callIdentity.isDirect) {
    return ensureOwnedCallUI(callIdentity, wasActive);
  }

  if (SERVICE.matching.sparkFallback && callIdentity.isSparkLeg) {
    log('Spark leg detected, refreshing service ownership');
  }

  return resolveOwnedServiceCall().then(function (ownedCall) {
    return ensureOwnedCallUI(ownedCall, wasActive);
  });
}

function handleCallDisconnect(ev) {
  var disconnectedCall = getCallIdentity(ev);
  var wasActive = state.isActiveCall;
  log('CallDisconnect', {
    CallId: disconnectedCall.callId,
    RemoteURI: disconnectedCall.uri,
    normalized: disconnectedCall.normalizedUri,
    matchedOwnedCall: matchesStoredOwnedCall(disconnectedCall),
  });

  if (matchesStoredOwnedCall(disconnectedCall)) {
    syncOwnedCallState(null);
  }

  return resolveOwnedServiceCall().then(function (ownedCall) {
    return ensureOwnedCallUI(ownedCall, wasActive);
  });
}

function handleParticipantUpdated(ev) {
  var uri = (ev && ev.Uri) ? ev.Uri : '';
  var wasActive = state.isActiveCall;
  rememberConferenceUri(uri);
  if (!isServiceParticipantUri(uri)) {
    return Promise.resolve();
  }
  rememberOwnedCallHint(ev);
  log('Matching service participant detected, refreshing ownership');
  return resolveOwnedServiceCall().then(function (ownedCall) {
    if (!ownedCall) return Promise.resolve();
    return ensureOwnedCallUI(ownedCall, wasActive);
  });
}

function handleWidgetAction(event) {
  var WidgetId = event.WidgetId;
  var Type = event.Type;
  var Value = event.Value;
  log('Widget.Action:', WidgetId, 'Type=', Type, 'Value=', Value);

  if (state.suppressWidgetAction) return Promise.resolve();

  var cfg = SERVICE.widgets[WidgetId];
  if (!cfg) return Promise.resolve();

  if (cfg.kind === 'button' && Type !== 'clicked') return Promise.resolve();
  if (cfg.kind === 'toggle' && Type !== 'changed') return Promise.resolve();

  if (cfg.kind === 'toggle') {
    return resolveOwnedServiceCall().then(function (ownedCall) {
      if (!ownedCall) {
        return xapi.Command.UserInterface.Extensions.Widget.SetValue({
          WidgetId: WidgetId,
          Value: 'off',
        }).catch(function () {});
      }
      return enforceExclusiveToggles(WidgetId, Value).then(function () {
        var dtmfCode = resolveWidgetDTMF(WidgetId);
        if (dtmfCode) return safeDTMF(dtmfCode, ownedCall);
      });
    });
  }

  var dtmfCode = resolveWidgetDTMF(WidgetId);
  if (dtmfCode) return safeDTMF(dtmfCode);
  return Promise.resolve();
}

function handlePanelClicked(ev) {
  if (ev && ev.PanelId === SERVICE.panels.home) {
    showMeetingPrompt();
  }
}

function handleTextInputResponse(ev) {
  if (ev && ev.FeedbackId === SERVICE.input.feedbackId) {
    return handleMeetingSubmit(ev);
  }
  return Promise.resolve();
}

function normalizeMuteStatus(ev) {
  return (ev && ev.Status != null) ? ev.Status
    : (ev && ev.Mute != null) ? ev.Mute
    : ev;
}

function handleVideoMuteChange(ev) {
  var status = normalizeMuteStatus(ev);
  if (!SERVICE.features.videoMuteDtmf) return Promise.resolve();
  if (status !== 'On' && status !== 'Off') return Promise.resolve();
  if (!hasMuteOwnershipHint()) return Promise.resolve();
  return resolveOwnedServiceCall().then(function (ownedCall) {
    if (!ownedCall) return Promise.resolve();
    if (state.lastVideoMuteStatus === status) return Promise.resolve();
    log('Video mute change event:', status, ev);
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
    log('Mic mute change event:', status, ev);
    state.lastMicMuteStatus = status;
    return safeDTMF(SERVICE.features.micMuteDtmf, ownedCall);
  });
}

/********************************************************
 * SECTION 10: BOOT
 ********************************************************/

function injectPanels() {
  xapi.command('Userinterface Extensions Panel Save', {
    PanelId: SERVICE.panels.home,
  }, HOME_PANEL_XML);

  if (SERVICE.features.codecVersionCheck) {
    return getCodecVersion().then(function (version) {
      var major = getMajorVersion(version);
      var useInCallType = major === 9;
      var placementLine = useInCallType
        ? '<Type>InCall</Type>'
        : '<Location>CallControls</Location>';
      var panelXml = buildControlsPanelXml(placementLine);
      return xapi.command('UserInterface Extensions Panel Save', {
        PanelId: SERVICE.panels.controls,
      }, panelXml).catch(function (err) {
        log('Failed to save controls panel:', err);
      });
    });
  } else {
    var panelXml = buildControlsPanelXml('<Location>CallControls</Location>');
    return xapi.command('UserInterface Extensions Panel Save', {
      PanelId: SERVICE.panels.controls,
    }, panelXml).catch(function (err) {
      log('Failed to save controls panel:', err);
    });
  }
}

function wireEvents() {
  xapi.Command.UserInterface.Extensions.Panel.Update({
    PanelId: SERVICE.panels.home,
    Visibility: 'Auto',
  }).catch(function () {});

  xapi.Command.UserInterface.Extensions.Panel.Update({
    PanelId: SERVICE.panels.controls,
    Visibility: 'Hidden',
  }).catch(function () {});

  xapi.Event.UserInterface.Extensions.Panel.Clicked.on(function (ev) {
    handlePanelClicked(ev);
  });

  xapi.Event.UserInterface.Message.TextInput.Response.on(function (ev) {
    handleTextInputResponse(ev);
  });

  if (SERVICE.matching.sparkFallback) {
    xapi.Event.Conference.ParticipantList.ParticipantUpdated.on(function (ev) {
      handleParticipantUpdated(ev).catch(function (e) {
        log('ParticipantUpdated handler error:', e);
      });
    });
  }

  xapi.Event.CallSuccessful.on(function (ev) {
    handleCallSuccessful(ev).catch(function (e) {
      log('CallSuccessful handler error:', e);
    });
  });

  xapi.Event.CallDisconnect.on(function (ev) {
    handleCallDisconnect(ev).catch(function (e) {
      log('CallDisconnect handler error:', e);
    });
  });

  if (SERVICE.features.videoMuteDtmf) {
    xapi.Status.Video.Input.MainVideoMute.on(function (ev) {
      handleVideoMuteChange(ev).catch(function (e) {
        log('Video mute handler error:', e);
      });
    });
  }

  if (SERVICE.features.micMuteDtmf) {
    xapi.Status.Audio.Microphones.Mute.on(function (ev) {
      handleMicMuteChange(ev).catch(function (e) {
        log('Mic mute handler error:', e);
      });
    });
  }

  xapi.Event.UserInterface.Extensions.Widget.Action.on(function (event) {
    handleWidgetAction(event);
  });
}

(function boot() {
  injectPanels();
  ensureHttpHostAllowed();
  wireEvents();

  delay(100).then(function () {
    var wasActive = state.isActiveCall;
    return resolveOwnedServiceCall().then(function (ownedCall) {
      if (!ownedCall) return Promise.resolve();
      return ensureOwnedCallUI(ownedCall, wasActive);
    });
  });
})();
