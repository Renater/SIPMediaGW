import xapi from 'xapi'; 

/********************************************************
 * SECTION 1: METADATA
 ********************************************************/

const METADATA = {
  name: 'WCE',
  version: 'WCE-10-Btn_v3_2',
  description: "Rendez-vous macro",
};

/********************************************************
 * SECTION 2: CONFIG (SERVICE)
 ********************************************************/

const SERVICE = {
  name: METADATA.name,
  version: METADATA.version,

  panels: {
    home: 'rdv_button',
    controls: 'rdv_controls',
    home_icon: 'rdv30a4a8a9d9fec55e624a54cf86bd0324247112efd3e70a6d82b607321b8b2',
    controls_icon:'incalleaf0d171f0b7bc7c2f5103f3ecf83461',
  },

  matching: {
    prefix: '1',
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
  },

  dtmf: {
    audio: '1',
    video: '2',
    conversation: '3',
    hand: '4',
    participants: '5',
    mozaic: '6',
    lock: '7',
    mute_all_micro: '8',
    menu: '#',
  },

  widgets: {
    rdv_ctrl_hand:         { kind: 'toggle', dtmf: 'hand' },
    rdv_ctrl_chat:         { kind: 'toggle', dtmf: 'conversation' },
    rdv_ctrl_mozaic:       { kind: 'toggle', dtmf: 'mozaic' },
    rdv_ctrl_participants: { kind: 'toggle', dtmf: 'participants' },
    rdv_ctrl_lock:         { kind: 'toggle', dtmf: 'lock' },
    rdv_ctrl_mute_all:     { kind: 'button', dtmf: 'mute_all_micro' },
    rdv_ctrl_menu:         { kind: 'button', dtmf: 'menu' },
  },

  input: {
    mode: 'single',
    feedbackId: 'rdv_meeting',
    inputType: 'SingleLine',
    placeholder: 'Saisissez un nom ou bien un code à 10 chiffres.',
    title: "Rendez-vous",
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
    <Name>Rendez-vous</Name>
    <ActivityType>Custom</ActivityType>
    <CustomIcon>
      <Content>iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAAAx3pUWHRSYXcgcHJvZmlsZSB0eXBlIGV4aWYAAHjabVDbDcMgDPxnio6AH4AZhzSJ1A06fm3sREnUkzgO2xzGaft+9vQyIHDi0qT2WrOCO3ccKiQ7xmTIPHmC3pGDezydCdQQWaUfpUb9EYfTwLehqlyMJIxguSc6h788jDA6s45Mr2HUw4jQExAGw7+Va5d2/cKy5TvEVzJadu3HZhSXn2duOr216DuEuBFQViYSb4Bs1URDRVFGaloI1FTTZJil4AP5N6cD6Qc1YlsNUS2g1QAAAYVpQ0NQSUNDIHByb2ZpbGUAAHicfZG/S8NAHMVfW0tFKh3sIOoQoTrZxYo4lioWwUJpK7TqYHLpL2jSkKS4OAquBQd/LFYdXJx1dXAVBMEfIP4B4qToIiV+Lym0iPHguA/v7j3u3gHeVo0pRl8cUFRTzyQTQr6wKgRe4ccoQhhHTGSGlsou5uA6vu7h4etdlGe5n/tzDMpFgwEegTjONN0k3iCe3TQ1zvvEYVYRZeJz4imdLkj8yHXJ4TfOZZu9PDOs5zLzxGFiodzDUg+ziq4QzxBHZEWlfG/eYZnzFmel1mCde/IXBovqSpbrNMeQxBJSSEOAhAaqqMFElFaVFAMZ2k+4+Edsf5pcErmqYORYQB0KRNsP/ge/uzVKsWknKZgA/C+W9TEBBHaBdtOyvo8tq30C+J6BK7Xrr7eAuU/Sm10tcgSEtoGL664m7QGXO8Dwkybqoi35aHpLJeD9jL6pAAzdAgNrTm+dfZw+ADnqavkGODgEJsuUve7y7v7e3v490+nvBwoYcuPiKcn1AAANdmlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQiPz4KPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iWE1QIENvcmUgNC40LjAtRXhpdjIiPgogPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4KICA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIgogICAgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iCiAgICB4bWxuczpzdEV2dD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlRXZlbnQjIgogICAgeG1sbnM6ZGM9Imh0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvIgogICAgeG1sbnM6R0lNUD0iaHR0cDovL3d3dy5naW1wLm9yZy94bXAvIgogICAgeG1sbnM6dGlmZj0iaHR0cDovL25zLmFkb2JlLmNvbS90aWZmLzEuMC8iCiAgICB4bWxuczp4bXA9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iCiAgIHhtcE1NOkRvY3VtZW50SUQ9ImdpbXA6ZG9jaWQ6Z2ltcDo1OTEwZTVlYS02ZTgzLTRmMmQtYmRlYy1jNjNjYWEzNmZiMmUiCiAgIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6ZGQyNmVjNGItYzk3ZC00ZmMxLThkNDEtNmZmY2M4Njg4NzEyIgogICB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6NDJlNTVkMjMtNWZlZS00NTRkLTgxZjAtYjhkOTFiNTY4NDEwIgogICBkYzpGb3JtYXQ9ImltYWdlL3BuZyIKICAgR0lNUDpBUEk9IjIuMCIKICAgR0lNUDpQbGF0Zm9ybT0iV2luZG93cyIKICAgR0lNUDpUaW1lU3RhbXA9IjE3Nzk4OTYyNDAyNTYwMjIiCiAgIEdJTVA6VmVyc2lvbj0iMi4xMC4zOCIKICAgdGlmZjpPcmllbnRhdGlvbj0iMSIKICAgeG1wOkNyZWF0b3JUb29sPSJHSU1QIDIuMTAiCiAgIHhtcDpNZXRhZGF0YURhdGU9IjIwMjY6MDU6MjdUMTc6Mzc6MTgrMDI6MDAiCiAgIHhtcDpNb2RpZnlEYXRlPSIyMDI2OjA1OjI3VDE3OjM3OjE4KzAyOjAwIj4KICAgPHhtcE1NOkhpc3Rvcnk+CiAgICA8cmRmOlNlcT4KICAgICA8cmRmOmxpCiAgICAgIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiCiAgICAgIHN0RXZ0OmNoYW5nZWQ9Ii8iCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6YzAzYjk2ZjYtYmFjZS00N2E3LTljYTEtYjFkNmM1MzA0Zjg5IgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJHaW1wIDIuMTAgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDI2LTA1LTI3VDE3OjM3OjIwIi8+CiAgICA8L3JkZjpTZXE+CiAgIDwveG1wTU06SGlzdG9yeT4KICA8L3JkZjpEZXNjcmlwdGlvbj4KIDwvcmRmOlJERj4KPC94OnhtcG1ldGE+CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAKPD94cGFja2V0IGVuZD0idyI/PoWam8kAAAAGYktHRAAAAAAAAPlDu38AAAAJcEhZcwAADsMAAA7DAcdvqGQAAAAHdElNRQfqBRsPJRTNho4NAAADWUlEQVRo3u2ZS08TURzFz8z0DRXaUqRA3y0LFRHlmWgVJS5IiN/BxJ2J7vwKLl34BUxcmbgwLogaJG4EDSEWAihgkUJJRWzLI9LOTGfciBFqSztth3a4Zzf35jb53Tn/M/f+CxARKUrUvw+PHo8/BDCkMMax+3f77+0/qA5NPlDgS20H8BeYPmmWJsAEmAATYAJMgAkwASbA5ZJK6kKthsHNQTfsrSaoVPLsG8umEVlP4M3oMpKptLzA1wIOuF0W7O1x2NlNygKs06rhdlkwcFXAyOuQvMCnG40QRRFPngbBsmlZgDUaBnduX0RDQ80x1DAFCIIoG+y+pTlOOJ4aBgBRlGBLHYOO9kaYTHrMzm1gdW1Xwl5TxwNciPR6FQavuw6EXJvfipVwHKNjy9jd5ZT1WQpctsPtsmQkutNhQn9vS3V8hwuxtMGgyR5GaqZaDh75E6eS2S0rSAmDSre0oSb7G2YYWlnAajWNZltd1nmP2wKKopRTwxwnIBb7lXV+LZKAKJOtZfPSs+ezYFk+YzyZ5PDi5UJBB56qAGZZAfOfNzLGl75uIp2uktAq1IYLi7GMsbn5TWXehw0GFXq6Mw8YlzptqK1VV/59OF95XKfQ3t4Ee2s9aDqzAL3eBrjdFoRX4/gUjCK8ulPOEi7y8pDLOjSF4SEfnE7z0TajKbicZricZiwu/cDIq1CFWjoHcXdXU16wh+X3WdHbbau+Gra31kle63TUVyYwnWO1Xic9iLTa7JVW7IlMcg2nUjzq6/S4cN6KWDx5MFQoFNXYU6loOB1GQDxYNWaTDhoNg8QWLz/w9EwUNwZqEbjiKbntjEYdbg2f+f/NShARnInKDzz/JYbo9yB8XhMYhjq68UIVf2LkeQGhbwls/kyWH9hi1qGvR1pnguMEvH23Ap4XstQsg4GA88/G5ZbVmtmxnPgYwc9YsrTANQY1vJ6GIgKOQmR9OyN0KApothnh91kl//bM7Ebpgbd3UhBFUXJKtvmtaPNbS1Ljwel1pFgePV0OpNMC4vH8LZ53lCa2WIx/CIPj5OtDZ9O5s03o7GhBKsXj/cQKdgroeBYUWpNTUUxORVHNIn+XEmACTIAJMAEmwASYABPgMgGHFMgYzXV56APQqTDgaRCdIP0G/+f5avdRVGoAAAAASUVORK5CYII=</Content>
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
    <Name>Interactions Rendez-vous</Name>
    <ActivityType>Custom</ActivityType>
    <CustomIcon>
      <Content>iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAAFVElEQVR42u1aXWhcRRT+zty7myxSyQ+oDfhiW8iToJCIQekiEmoRBN9EsVXxpSJC/YH4pBARQ9XXQghpDL4IgqFIK6wgpbhL+2DFN4nmQawWKzRkkf2Zmc+HzKw36ya5m727ZDd74HIvd+feO9/M+b5z5swCfetb3/rWt751l5GUAwmWZHAgQBeLPNzzoD0wTb5EcoPkFZLH/ayTVD0JmORF/meG5HseLMmwlwB7UJdIWpJldybJb0ke9QPTE6LmARvDyw6kdueqO/9F8rme4fYOgOuvz5O8q+tdfBfAdO7t7/1YqXDCP7efBa2VjgmAAIAG8GAqhSsk3xARKyK20y7eso7EmGHWqbe3L33cJhl2QtCaGVyVoKfQAgbAs5kMCtUqT4qIjg5eO2aVpBIRw2LxMMmBTs0wGwmaMfzQC1nSgua0Qtz1aZK3WS4/tOcBbgGwd3Hv5ldIjicZsyNJkSJ5rvbVSmViNxdPxNWMMbDW1r9XOUF7HECe5CkRMSLCVgSNZCgihuR9AL4G8Kb7DjvCYWstgiCAUqoeNACE2OT1EIALJBduk3e7Dod74GsoIprkIwCuAjjhwAYuarQfsFIKhUIBq6urUEqB/N9AB270DYCXR4F8hZxyHY8Vs30b98wpAN8BOOLeGSYmCjtx2JhNii4sLBAAh4eHef36dVpra781MJ+WVki+HSesbOGrMee2CYU2LodbBjw5OUkRIQDOzMxsoqpWGSdmG8OLJO/frpMRhb/XGHMp0g/bIOtrj2h5gfLHoUOHQBIigoGBgdr9BkK2JWYD0ErhaQAFks84Xqs6cdIkJwFcVUo1zddEAHuBCsMQSimIiO8g0uk0lFJIp9O1djukpV7QxgB8RfIDl5IqkiIimlq/6Ph61IFtma9hMzMbBAEWFxexvLxcU+UbN27U2szPzyOXy22+OAwxOzuLiYkJWGu3Ax8AsG7G3yX5m4icJ5ki+T6AGR8MEhOnZjicz+fpOhfrGB0d5fr6Oq21tNbuxOuSO19w3x4iue7ulWMkOu3h8NDQEEZGRmK3P3bsGFKp1G7NNIABAL+XgY+cO98BkAXwE4C0c30mMZFNufT4+DhyuRxWVlZq3F1aWsLa2hoAIJvNIpvNwlqLdDqNM2fOIJPJ1ESt3okicfR7AC8Miqw5DkNEfiA5BeATAK/6bjgadMalG7nl9PR0zYXn5uaaybX9yxb8KqdOpYPI9fMk/66L5e13aRGBtRZaa1QqldpZRKCUwsbGBrTWKJVK0Fo3yrr8LClrQQBnReQVESm7ZZ6NfMu4dDIQkc9RLj/qFDt0A2w7EpZ8SPKHtRYkYa3dcj8Mw0Zu7OPon0rhKRH51K+gomAjoOnzbhkc/BnAkwBmI303Hatp+UyrUChwbGyMU1NTvHnz5naKbCOumCf5QLNr5Lr17zTJXyMubtqeWkatWCxSax2Hr4skB/faKb9ictf3kPxiS57eCcDRhUKDmdUR0Gfr351EDYvkayT/6egMb+PG3oX/qFZ5Iuldiuj+Fsvlh0l+THJkzxXMFko8Ub4WSB5pZ5G+2dlMuppoIwnNEoCsiPziQotuB2C/yopbEk4SsIks/d4SkdMiUvJl1Hbm/a74r926PJnUMkY+HAK4BeC0iFx2rmYbxddu3Wrx+bAHe61UwmMObOgrlL20txTl62cAspmMrPpKBbrNYm6XGr21GNe9f4OIsSF+q1rlyaTj634CXI2AvRb5y0NXbYKrmMJkInxdBnBcpIv5uksB/JtIPvxOT/B1F8Cvk8xXySd6hq/tylv3o0kMkL5N21PEvvWtb33rW98OmP0LBaBk+yxaihEAAAAASUVORK5CYII=</Content>
      <Id>${SERVICE.panels.controls_icon}</Id>
    </CustomIcon>
    <Page>
      <Name>Rendez-vous</Name>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_6</WidgetId>
          <Name>👋 Lever la main</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>rdv_ctrl_hand</WidgetId>
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
          <WidgetId>rdv_ctrl_chat</WidgetId>
          <Name>Chat</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_8</WidgetId>
          <Name>🔳 Mosaïque</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>rdv_ctrl_mozaic</WidgetId>
          <Name>Mode mosaïque</Name>
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
          <WidgetId>rdv_ctrl_participants</WidgetId>
          <Name>Participants</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>widget_10</WidgetId>
          <Name>🔐 Verrouiller la conférence</Name>
          <Type>Text</Type>
          <Options>size=3;fontSize=normal;align=center</Options>
        </Widget>
        <Widget>
          <WidgetId>rdv_ctrl_lock</WidgetId>
          <Name>Verrouiller</Name>
          <Type>ToggleButton</Type>
          <Options>size=1</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>rdv_ctrl_mute_all</WidgetId>
          <Name>🎤 Couper tous les micros</Name>
          <Type>Button</Type>
          <Options>size=3</Options>
        </Widget>
      </Row>
      <Row>
        <Name>Row</Name>
        <Widget>
          <WidgetId>rdv_ctrl_menu</WidgetId>
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
    errorTitle: 'Le nom de conférence est invalide.',
    errorText: 'Saisissez au minimum 10 caractères ASCII (sans accents) dont au moins 3 chiffres, ou un code de 10 chiffres.',
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
  // Force delete panels before re-injecting to avoid icon cache issues
  xapi.Command.UserInterface.Extensions.Panel.Remove({ PanelId: SERVICE.panels.home }).catch(function () {});
  xapi.Command.UserInterface.Extensions.Panel.Remove({ PanelId: SERVICE.panels.controls }).catch(function () {});

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