import { useEffect, useRef, useState } from "react";

// Redesenha quando o dispositivo muda (o "loop" dele roda a cada 50 ms).
function useDispositivo(disp) {
  const [, setVersao] = useState(0);
  useEffect(() => disp.assinar(() => setVersao((v) => v + 1)), [disp]);
  return disp;
}

function Led({ cor, aceso, rotulo }) {
  return (
    <span className={`d-led d-led-${cor}${aceso ? " aceso" : ""}`}>
      <i aria-hidden="true" />
      {rotulo}
    </span>
  );
}

function Tanque({ t }) {
  const nivel = 62;
  const cor = t.temperatura >= 80 ? "#e46f63" : t.temperatura >= 60 ? "#f0a35e" : "#7db7e8";
  return (
    <svg viewBox="0 0 320 170" className="d-tanque" role="img" aria-label={`Tanque a ${t.temperatura.toFixed(1)} °C`}>
      <rect x="40" y="20" width="240" height="140" rx="10" fill="#f2eef4" stroke="#8a7f90" strokeWidth="3" />
      <rect x="43" y={nivel} width="234" height={155 - nivel} rx="6" fill={cor} />
      <g transform={`translate(0 ${t.cesto ? 48 : 0})`}>
        <rect x="120" y="6" width="80" height="50" rx="6" fill="none" stroke="#5B2A6E" strokeWidth="3" strokeDasharray="6 4" />
        {[[138, 40], [156, 44], [174, 40], [147, 28], [166, 28]].map(([x, y]) => (
          <circle key={`${x}${y}`} cx={x} cy={y} r="7" fill="#3B1747" />
        ))}
      </g>
      <rect x="58" y="50" width="6" height="95" fill="#6b6470" />
      <circle cx="61" cy="145" r="6" fill="#6b6470" />
      <path d="M240 150 q8 -8 16 0 q8 8 16 0" stroke={t.esquentando ? "#e4572e" : "#999"} strokeWidth="5" fill="none" />
    </svg>
  );
}

export default function Bancada({ disp }) {
  useDispositivo(disp);
  const t = disp.tanque;
  const [entrada, setEntrada] = useState("");
  const serialRef = useRef(null);
  const apertadoEm = useRef(null);
  const [apertado, setApertado] = useState(false);

  useEffect(() => {
    const el = serialRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [disp.serial.length]);

  // Clique = toque rápido; segurar 5 s = modo termômetro (parado) ou cancelar o lote (preparando).
  const apertar = () => {
    apertadoEm.current = Date.now();
    setApertado(true);
  };
  const soltar = () => {
    if (apertadoEm.current == null) return;
    const duracao = Date.now() - apertadoEm.current;
    apertadoEm.current = null;
    setApertado(false);
    if (duracao >= 5000) disp.segurou();
    else disp.toque();
  };

  const buzzer = Date.now() < disp.buzzerAte;
  const ocupado = Boolean(disp.automatico) || disp.estado !== "OCIOSO";

  return (
    <div className="d-bancada">
      <section className="d-card">
        <h2 className="d-titulo">Tanque de branqueamento</h2>
        <Tanque t={t} />
        <div className="d-linha d-entre">
          <div>
            <div className="d-rotulo">Água</div>
            <div className={`d-grande${t.temperatura >= 80 ? " d-quente" : ""}`}>
              {t.sensor ? `${t.temperatura.toFixed(1).replace(".", ",")} °C` : "sem sensor"}
            </div>
          </div>
          <div className="d-direita">
            <div className="d-rotulo">Aquecedor</div>
            <span className={`d-chip${t.esquentando ? " d-chip-laranja" : ""}`}>
              {!t.aquecedor ? "desligado" : t.esquentando ? "esquentando" : "no termostato"}
            </span>
          </div>
        </div>
        <div className="d-linha">
          <button type="button" className="d-botao d-principal" disabled={ocupado} onClick={() => disp.loteCompleto("aprovado")}>
            Fazer um lote aprovado
          </button>
          <button type="button" className="d-botao" disabled={ocupado} onClick={() => disp.loteCompleto("reprovado")}>
            Fazer um lote reprovado
          </button>
        </div>
        <p className="d-dica">
          {disp.automatico ? `Fazendo um lote ${disp.automatico}…` : "Um clique faz o lote inteiro, como o batedor: novo lote, "
            + "cesto na água e toque no botão aos 12 s (aprovado) ou aos 5 s (reprovado). Uns 10 s depois o dispositivo envia."}
        </p>
        <div className="d-linha">
          <button type="button" className="d-botao" onClick={() => disp.mergulhar()} disabled={t.cesto}>Mergulhar o cesto</button>
          <button type="button" className="d-botao" onClick={() => disp.retirar()} disabled={!t.cesto}>Tirar o cesto</button>
        </div>
        <div className="d-linha">
          <button type="button" className="d-botao" onClick={() => { t.manual = null; t.temperatura = 30; }}>Água fria (30 °C)</button>
          <button type="button" className="d-botao" onClick={() => { t.manual = null; t.temperatura = 86; }}>Água quente (86 °C)</button>
        </div>
        <label className="d-linha">
          <span className="d-rotulo-campo">Termostato</span>
          <input type="range" min="60" max="98" step="0.5" value={t.setpoint}
                 onChange={(e) => { t.setpoint = Number(e.target.value); disp.avisar(); }} />
          <b>{t.setpoint.toFixed(1).replace(".", ",")} °C</b>
        </label>
        <div className="d-linha">
          <label className="d-check"><input type="checkbox" checked={t.aquecedor}
                 onChange={(e) => { t.aquecedor = e.target.checked; disp.avisar(); }} /> aquecedor ligado</label>
          <label className="d-check"><input type="checkbox" checked={t.sensor}
                 onChange={(e) => { t.sensor = e.target.checked; disp.avisar(); }} /> sensor conectado</label>
        </div>
      </section>

      <section className="d-card">
        <h2 className="d-titulo">Dispositivo ORK01</h2>
        <div className="d-linha d-dispositivo">
          <button type="button" className={`d-botao-fisico${apertado ? " apertado" : ""}`} aria-label="Botão do dispositivo"
                  onPointerDown={(e) => { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); apertar(); }}
                  onPointerUp={soltar} onPointerCancel={soltar}>
            BOTÃO
          </button>
          <div className="d-leds">
            <Led cor="verde" aceso={disp.leds.verde} rotulo="verde" />
            <Led cor="vermelho" aceso={disp.leds.vermelho} rotulo="vermelho" />
            <Led cor="buzzer" aceso={buzzer} rotulo="buzzer" />
            <span className="d-chip">{disp.rotuloEstado()}</span>
          </div>
        </div>
        <p className="d-dica">
          Passo a passo: <b>BOTÃO</b> (novo lote) → verde piscando → <b>Mergulhar o cesto</b> → <b>BOTÃO</b> (começa a
          contar) → apito dos 10 s → <b>BOTÃO</b> de novo para fechar. Só tirar o cesto não fecha o ciclo (fecha
          sozinho em 60 s). Segurar o botão 5 s: modo termômetro.
        </p>
        <div className="d-linha">
          <label className="d-check"><input type="checkbox" checked={disp.wifi}
                 onChange={(e) => disp.ligarWifi(e.target.checked)} /> roteador Wi-Fi ligado</label>
        </div>
        <div className="d-linha">
          <span className="d-rotulo-campo">Relógio</span>
          <button type="button" className="d-botao" onClick={() => disp.ajustarRelogio(-600_000)}>Atrasar 10 min</button>
          <button type="button" className="d-botao" onClick={() => disp.ajustarRelogio(600_000)}>Adiantar 10 min</button>
        </div>
        <p className="d-dica">
          Hora do dispositivo: {new Date(disp.agoraRtc()).toLocaleTimeString("pt-BR", { timeZone: "America/Belem" })}
          {disp.rtcOffset ? ` (${disp.rtcOffset > 0 ? "+" : "−"}${Math.abs(disp.rtcOffset / 60000)} min)` : ""}
          {" · "}Fila: {disp.pendentes.length} pendente(s), {disp.enviados} enviado(s), {disp.recusados.length} recusado(s)
          {disp.ultimoEnvio ? ` · Último envio: ${disp.ultimoEnvio}` : ""}
        </p>
      </section>

      <section className="d-card">
        <h2 className="d-titulo">Monitor serial</h2>
        <pre className="d-serial" ref={serialRef}>
          {disp.serial.map((l, i) => (
            <span key={i} className={/APROVADO/.test(l) ? "aprov" : /REPROVADO|RECUSADO/.test(l) ? "reprov" : /^>/.test(l) ? "cmd"
              : /Envio|Wi-Fi/.test(l) ? "env" : ""}>{l}{"\n"}</span>
          ))}
        </pre>
        <form className="d-linha" onSubmit={(e) => { e.preventDefault(); disp.comando(entrada); setEntrada(""); }}>
          <input className="d-entrada" value={entrada} onChange={(e) => setEntrada(e.target.value)}
                 placeholder="comando (ex.: fila, adulterar 33)" aria-label="Comando do Monitor serial" />
          <button type="submit" className="d-botao">Enviar</button>
        </form>
        <div className="d-linha">
          {["ajuda", "fila", "enviar"].map((c) => (
            <button key={c} type="button" className="d-botao d-pequeno" onClick={() => disp.comando(c)}>{c}</button>
          ))}
        </div>
      </section>

      <section className="d-card">
        <h2 className="d-titulo">Eventos</h2>
        {disp.eventos.length === 0 ? <p className="d-dica">Nada ainda.</p> : (
          <ul className="d-eventos">{disp.eventos.map((e, i) => <li key={i}>{e}</li>)}</ul>
        )}
      </section>
    </div>
  );
}
