/**
 * Gmail Inbox Bridge — Google Apps Script
 * Lets the outreach system read replies and send responses from Jake's real Gmail,
 * over a single secret HTTPS URL (works where IMAP/SMTP are blocked).
 *
 * SETUP (all on your phone):
 *  1. Go to script.google.com → New project.
 *  2. Delete everything, paste ALL of this file.
 *  3. Change SECRET below to any random word only you know.
 *  4. Click Deploy → New deployment → type "Web app".
 *     - Execute as: Me
 *     - Who has access: Anyone
 *     - Deploy → Authorize access → pick your Google account → Allow.
 *  5. Copy the "Web app URL" it gives you and send it to me, along with your SECRET.
 *
 * Security: every request must carry the secret token, so only I can use it.
 * You can revoke it anytime: Deploy → Manage deployments → Archive.
 */

var SECRET = "CHANGE_ME_to_a_random_word";

// READ: GET <url>?token=SECRET&days=4  -> recent inbound emails as JSON
function doGet(e) {
  if (!e || e.parameter.token !== SECRET) return _json({ error: "unauthorized" });
  var days = parseInt(e.parameter.days || "4", 10);
  var me = (Session.getActiveUser().getEmail() || "").toLowerCase();
  // in:anywhere catches replies that land in Spam; -from:me excludes own sent mail server-side.
  var threads = GmailApp.search('newer_than:' + days + 'd in:anywhere -in:trash -in:drafts -in:chats -from:me', 0, 50);
  var out = [];
  threads.forEach(function (t) {
    t.getMessages().forEach(function (m) {
      var from = m.getFrom().toLowerCase();
      if (me && from.indexOf(me) !== -1) return; // only skip own mail when we actually know our address
      out.push({
        from: m.getFrom(),
        to: m.getTo(),
        subject: m.getSubject(),
        date: m.getDate().toISOString(),
        body: m.getPlainBody().slice(0, 4000),
        threadId: t.getId(),
        messageId: m.getId()
      });
    });
  });
  return _json({ messages: out });
}

// SEND: POST <url>  body {token, to, subject, body, threadId?}
// Replies inside the existing thread when threadId is given; else sends fresh.
function doPost(e) {
  var p;
  try { p = JSON.parse(e.postData.contents); } catch (err) { return _json({ error: "bad json" }); }
  if (!p || p.token !== SECRET) return _json({ error: "unauthorized" });
  if (!p.to || !p.body) return _json({ error: "missing to/body" });
  try {
    if (p.threadId) {
      var t = GmailApp.getThreadById(p.threadId);
      // reply() goes only to the thread's last sender (the customer), not every participant.
      if (t) { t.reply(p.body); return _json({ ok: true, mode: "reply" }); }
    }
    GmailApp.sendEmail(p.to, p.subject || "Re:", p.body);
    return _json({ ok: true, mode: "new" });
  } catch (err) {
    return _json({ error: String(err) });
  }
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
