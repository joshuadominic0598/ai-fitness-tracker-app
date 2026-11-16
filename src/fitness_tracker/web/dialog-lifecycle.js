/* Keep queued native close events from clearing or blocking the next editor. */
(function (root) {
  "use strict";
  function create(dialog, onClosed) {
    let revision = 0,
      closing = null;
    dialog.addEventListener("close", () => {
      const finished = closing;
      closing = null;
      if (!dialog.open && (!finished || finished.revision === revision))
        onClosed();
      if (finished) finished.resolve();
    });
    function show() {
      const requested = ++revision;
      const open = () => {
        if (requested !== revision) return;
        if (!dialog.open) dialog.showModal();
        dialog.scrollTop = 0;
      };
      if (closing) closing.promise.then(open);
      else open();
    }
    function close() {
      if (closing) return closing.promise;
      if (!dialog.open) return Promise.resolve();
      let resolve;
      const promise = new Promise((done) => {
        resolve = done;
      });
      closing = { revision, promise, resolve };
      dialog.close();
      return promise;
    }
    return { show, close };
  }
  if (typeof module !== "undefined" && module.exports)
    module.exports = { create };
  else root.DialogLifecycle = { create };
})(globalThis);
