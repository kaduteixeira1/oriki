import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "./estilo.css";
import App from "./App.jsx";
import { LayoutProvider } from "./layout.jsx";
import { iniciarSincronizacao } from "./fila.js";

// OR-19: reenvia os lotes salvos no celular quando a internet volta.
iniciarSincronizacao();

// OR-20: app instalável e que abre sem internet. Só no build: em desenvolvimento o cache
// atrapalharia o recarregamento automático do Vite.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <LayoutProvider>
        <App />
      </LayoutProvider>
    </BrowserRouter>
  </StrictMode>,
);
