/* Habilita+ — melhorias progressivas.
 * O site funciona sem este arquivo: tudo aqui só deixa a experiência melhor.
 * Fica num arquivo separado (e não em <script> no HTML) porque a política de
 * segurança do site (CSP) bloqueia scripts embutidos na página. */
(function () {
    "use strict";

    // Confirmação antes de ações destrutivas: <form data-confirmar="Texto?">
    document.addEventListener("submit", function (evento) {
        var formulario = evento.target;
        var pergunta = formulario.getAttribute("data-confirmar");
        if (pergunta && !window.confirm(pergunta)) {
            evento.preventDefault();
            return;
        }

        // Estado de envio: desativa o botão para evitar clique duplo (que, num
        // agendamento, tentaria marcar a mesma aula duas vezes) e mostra progresso.
        var botao = evento.submitter || formulario.querySelector("[type=submit]");
        if (botao && botao.hasAttribute("data-enviando")) {
            botao.setAttribute("aria-busy", "true");
            botao.classList.add("enviando");
            botao.dataset.textoOriginal = botao.textContent;
            botao.textContent = botao.getAttribute("data-enviando");
            // Adiado: desativar no mesmo instante impediria o próprio envio.
            window.setTimeout(function () { botao.disabled = true; }, 0);
        }
    });

    // Se a pessoa voltar pela setinha do navegador, o botão não fica travado.
    window.addEventListener("pageshow", function () {
        document.querySelectorAll("button.enviando").forEach(function (botao) {
            botao.disabled = false;
            botao.classList.remove("enviando");
            botao.removeAttribute("aria-busy");
            if (botao.dataset.textoOriginal) botao.textContent = botao.dataset.textoOriginal;
        });
    });

    document.addEventListener("DOMContentLoaded", function () {
        // Botão "Mostrar senha": escondido no HTML, só aparece com JavaScript.
        document.querySelectorAll("[data-alternar-senha]").forEach(function (botao) {
            var campo = document.getElementById(botao.getAttribute("data-alternar-senha"));
            if (!campo) return;
            botao.hidden = false;
            botao.setAttribute("aria-controls", campo.id);
            botao.setAttribute("aria-pressed", "false");
            botao.addEventListener("click", function () {
                var mostrar = campo.type === "password";
                campo.type = mostrar ? "text" : "password";
                botao.textContent = mostrar ? "Ocultar" : "Mostrar";
                botao.setAttribute("aria-pressed", String(mostrar));
            });
        });

        // Filtros: recolhidos no celular (resultados primeiro), abertos no desktop.
        var largo = window.matchMedia("(min-width: 1024px)");
        function ajustarFiltros() {
            document.querySelectorAll("details[data-abrir-no-desktop]").forEach(function (painel) {
                if (largo.matches) painel.open = true;
            });
        }
        ajustarFiltros();
        largo.addEventListener("change", ajustarFiltros);
    });

    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register("/service-worker.js").catch(function () {
                // Navegadores sem HTTPS ou embutidos em apps podem recusar o registro.
                // O site continua funcionando normalmente, apenas sem instalação.
            });
        });
    }
})();
