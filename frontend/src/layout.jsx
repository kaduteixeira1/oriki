// Alternância entre o layout de celular (coluna de 420 px, o do protótipo) e o layout web (largo, com
// colunas e menu na barra). A escolha fica guardada no aparelho; sem escolha, telas largas abrem no web.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const CHAVE = "oriki-layout";
const LayoutContexto = createContext({ modo: "mobile", alternar: () => {}, definir: () => {} });

function modoInicial() {
  try {
    const salvo = localStorage.getItem(CHAVE);
    if (salvo === "mobile" || salvo === "web") return salvo;
  } catch {
    // navegação privada ou armazenamento bloqueado: segue com o automático
  }
  return window.matchMedia?.("(min-width: 1024px)").matches ? "web" : "mobile";
}

export function LayoutProvider({ children }) {
  const [modo, setModo] = useState(modoInicial);

  useEffect(() => {
    document.documentElement.dataset.layout = modo;
  }, [modo]);

  const definir = useCallback((novo) => {
    setModo(novo);
    try {
      localStorage.setItem(CHAVE, novo);
    } catch {
      // sem armazenamento: vale só até recarregar
    }
  }, []);
  const alternar = useCallback(() => definir(modo === "web" ? "mobile" : "web"), [modo, definir]);
  const valor = useMemo(() => ({ modo, alternar, definir }), [modo, alternar, definir]);

  return <LayoutContexto.Provider value={valor}>{children}</LayoutContexto.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLayout() {
  return useContext(LayoutContexto);
}

export function BotaoLayout({ className = "botao-barra botao-icone" }) {
  const { modo, alternar } = useLayout();
  const paraWeb = modo === "mobile";
  return (
    <button type="button" className={className} onClick={alternar}
            aria-label={paraWeb ? "Mudar para a versão web" : "Mudar para a versão de celular"}
            title={paraWeb ? "Versão web" : "Versão celular"}>
      {paraWeb ? (
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="2.5" width="10" height="19" rx="2" /><path d="M11 18.5h2" /></svg>
      )}
      <span className="rotulo-layout">{paraWeb ? "Web" : "Celular"}</span>
    </button>
  );
}
