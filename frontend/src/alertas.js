// Tipos de alerta do painel do fiscal (seção 9.3 do plano + OR-31), do mais grave para o menos.
export const ALERTAS = {
  licenca_vencida: { rotulo: "Licença vencida", tipo: "erro" },
  envios_recusados: { rotulo: "Envio recusado", tipo: "erro" },
  lacuna_contador: { rotulo: "Registro faltando", tipo: "erro" },
  ciclos_reprovados: { rotulo: "Ciclos reprovados", tipo: "erro" },
  relogio_divergente: { rotulo: "Relógio fora de hora", tipo: "alerta" },
  dispositivo_sem_contato: { rotulo: "Dispositivo sem contato", tipo: "alerta" },
  sem_registro: { rotulo: "Sem registro", tipo: "alerta" },
  licenca_vence_em_breve: { rotulo: "Licença vencendo", tipo: "alerta" },
};
export const ORDEM_ALERTAS = Object.keys(ALERTAS);
