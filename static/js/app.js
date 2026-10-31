function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }
  return "";
}

const copilotForm = document.getElementById("copilot-form");
if (copilotForm) {
  copilotForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("copilot-status");
    const output = document.getElementById("copilot-response");
    const provider = document.getElementById("provider-label");
    status.textContent = "Thinking...";
    const formData = new FormData(copilotForm);
    try {
      const response = await fetch(window.location.href, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: formData,
      });
      const data = await response.json();
      if (!data.ok) {
        throw new Error("The copilot could not answer that question.");
      }
      output.textContent = data.content;
      provider.textContent = data.generated_by_ai ? "Powered by Gemini AI" : "Rule-based fallback mode";
      status.textContent = "";
    } catch (error) {
      status.textContent = "The copilot request failed. You can retry, or the server will use fallback mode on a normal submit.";
      copilotForm.submit();
    }
  });
}

document.querySelectorAll(".copy-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    const field = document.getElementById(button.dataset.target);
    if (!field) {
      return;
    }
    field.select();
    try {
      await navigator.clipboard.writeText(field.value);
      button.textContent = "Copied";
    } catch (error) {
      document.execCommand("copy");
      button.textContent = "Copied";
    }
  });
});
