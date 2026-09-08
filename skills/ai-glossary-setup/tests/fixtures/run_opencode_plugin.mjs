// Test harness for the generated Opencode plugin file. Loads the plugin as
// a real ES module, invokes its `session.idle` event handler with a mocked
// `client` (so the plugin's own subprocess-spawning and reporting code runs
// unmodified against the real `curate` command), and prints the recorded
// `client.tui.showToast` calls plus any thrown error as JSON on stdout. This
// lets Python assert on adapter-level observable behavior — toast content,
// variant, and whether the event handler itself ever threw — without
// reimplementing or mocking the plugin's own logic.
//
// Usage: node run_opencode_plugin.mjs <plugin-file> <messages-json>

import { pathToFileURL } from "node:url";

async function main() {
  const [pluginPath, messagesJson] = process.argv.slice(2);
  const mod = await import(pathToFileURL(pluginPath).href);
  const factory = Object.values(mod).find((value) => typeof value === "function");

  const toastCalls = [];
  const client = {
    session: {
      messages: async () => ({ data: JSON.parse(messagesJson) }),
    },
    tui: {
      showToast: async (input) => {
        toastCalls.push(input);
        return true;
      },
    },
  };

  let error = null;
  try {
    const hooks = await factory({ client });
    await hooks.event({
      event: { type: "session.idle", properties: { sessionID: "test-session" } },
    });
  } catch (caught) {
    error = String((caught && caught.message) || caught);
  }

  process.stdout.write(JSON.stringify({ toastCalls, error }));
}

main().catch((caught) => {
  process.stdout.write(JSON.stringify({ toastCalls: [], error: String((caught && caught.message) || caught) }));
  process.exitCode = 0;
});
