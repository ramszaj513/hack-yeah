const app = document.querySelector<HTMLElement>("#app")!;

function section(title: string, body: string): HTMLElement {
  const block = document.createElement("section");
  block.className = "status";
  const heading = document.createElement("h2");
  heading.className = "group-title";
  heading.textContent = title;
  const paragraph = document.createElement("p");
  paragraph.className = "basis";
  paragraph.textContent = body;
  block.append(heading, paragraph);
  return block;
}

function render(): void {
  app.replaceChildren();
  const shell = document.createElement("section");
  shell.className = "shell";

  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Extension settings";
  const title = document.createElement("h1");
  title.textContent = "Privacy";
  const intro = document.createElement("p");
  intro.className = "intro";
  intro.textContent = "Checks start only when you click Check this video. Nothing is scanned in the background.";
  shell.append(eyebrow, title, intro);

  shell.append(
    section("What is sent", "Only the selected video's ID, title, description, and available English captions are sent to the local fact-checking backend."),
    section("What is stored", "Results stay in Chrome session storage for the current browser session. They are not written to disk by this extension and are cleared when the browser closes."),
    section("What is not collected", "No browsing history, YouTube login, cookies, or account credentials are collected. Speech-to-text is not used."),
  );

  const clear = document.createElement("button");
  clear.className = "check";
  clear.type = "button";
  clear.textContent = "Clear session results";
  const status = document.createElement("p");
  status.className = "warning";
  clear.addEventListener("click", () => {
    clear.disabled = true;
    chrome.runtime.sendMessage({ type: "CLEAR_SESSION" }, () => {
      status.textContent = chrome.runtime.lastError
        ? "Could not clear session results. Reload the extension and try again."
        : "Session results cleared.";
      clear.disabled = false;
    });
  });
  shell.append(clear, status);
  app.append(shell);
}

render();
