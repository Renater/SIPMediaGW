const platforms = {
  jitsi: { name: "Jitsi Meet", needsApi: true },
  bigbluebutton: { name: "Big Blue Button", needsApi: true },
  visio: { name: "Visio", needsApi: false },
  teams: { name: "Teams", needsPin: true }
};

const select = document.getElementById("platform");
const meetingName = document.getElementById("meeting-name");
const teamsFields = document.getElementById("teams-fields");
const result = document.getElementById("result");

Object.entries(platforms).forEach(([key, p]) => {
  const opt = document.createElement("option");
  opt.value = key;
  opt.textContent = p.name;
  select.appendChild(opt);
});

select.addEventListener("change", () => {
  const p = platforms[select.value];
  meetingName.style.display = p.needsPin ? "none" : "block";
  teamsFields.style.display = p.needsPin ? "block" : "none";
});

document.getElementById("generate").addEventListener("click", generateSip);

async function generateSip() {
  try {
    let id;

    if (platforms[select.value].needsPin) {
      const meetingId = document.getElementById("teamsId").value.trim();
      const pin = document.getElementById("teamsPin").value.trim();
      if (!meetingId || !pin) throw "ID ou PIN manquant";
      id = `${meetingId}-${pin}`;
    } else {
      const conf = document.getElementById("conf").value.trim();
      if (!conf) throw "Nom de réunion manquant";

      if (platforms[select.value].needsApi) {
        const url = `https://rendez-vous.renater.fr/conf-api/conferenceMapper?conference=${conf}0@rendez-vous.renater.fr`;
        const data = await (await fetch(url)).json();
        id = data.id;
      } else {
        id = conf;
      }
    }

    result.innerHTML = `✅ URI SIP :<br><code>${id}@rdv.visio.renater.fr</code>`;
  } catch (e) {
    result.textContent = `❌ ${e}`;
  }
}
