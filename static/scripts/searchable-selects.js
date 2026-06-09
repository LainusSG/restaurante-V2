(function () {
    const instances = new WeakMap();

    function normalizar(texto) {
        return (texto || "")
            .toString()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase();
    }

    function etiquetaSelect(select) {
        const field = select.closest(".form-field");
        const label = field ? field.querySelector(".form-field__label") : null;
        return label ? label.textContent.replace("*", "").trim().toLowerCase() : "opcion";
    }

    function obtenerOpciones(select) {
        return Array.from(select.options).map((option) => ({
            value: option.value,
            text: option.textContent.trim(),
            disabled: option.disabled,
        }));
    }

    function opcionSeleccionada(select) {
        return select.options[select.selectedIndex] || null;
    }

    function refrescarPlaceholder(select, input) {
        const selected = opcionSeleccionada(select);
        const tieneValor = selected && selected.value;
        input.placeholder = tieneValor
            ? selected.textContent.trim()
            : `Buscar o seleccionar ${etiquetaSelect(select)}...`;
        if (!document.activeElement || document.activeElement !== input) {
            input.value = tieneValor ? selected.textContent.trim() : "";
        }
    }

    function cerrarTodos(excepto) {
        document.querySelectorAll(".searchable-select.is-open").forEach((elemento) => {
            if (elemento !== excepto) {
                elemento.classList.remove("is-open");
            }
        });
    }

    function renderizarOpciones(select, contenedor, filtro) {
        const estado = instances.get(select);
        if (!estado) return;

        const busqueda = normalizar(filtro);
        const opciones = obtenerOpciones(select).filter((option) => {
            if (!busqueda) return true;
            return normalizar(option.text).includes(busqueda);
        });

        estado.lista.innerHTML = "";

        if (!opciones.length) {
            const vacio = document.createElement("div");
            vacio.className = "searchable-select__empty";
            vacio.textContent = "Sin resultados";
            estado.lista.appendChild(vacio);
            return;
        }

        opciones.forEach((option) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "searchable-select__option";
            button.textContent = option.text || "Sin seleccionar";
            button.disabled = option.disabled;
            button.dataset.value = option.value;
            button.setAttribute("role", "option");
            button.setAttribute("aria-selected", String(option.value === select.value));

            button.addEventListener("mousedown", (event) => {
                event.preventDefault();
            });

            button.addEventListener("click", () => {
                select.value = option.value;
                estado.input.value = option.value ? option.text : "";
                refrescarPlaceholder(select, estado.input);
                contenedor.classList.remove("is-open");
                select.dispatchEvent(new Event("change", { bubbles: true }));

                window.setTimeout(() => {
                    refrescarSelectsBuscables();
                }, 0);
            });

            estado.lista.appendChild(button);
        });
    }

    function crearSelectBuscable(select) {
        if (instances.has(select) || select.multiple) return;

        const wrapper = select.closest(".form-field__input-wrapper") || select.parentElement;
        if (!wrapper) return;

        const originalRequired = select.required;
        select.dataset.originalRequired = originalRequired ? "true" : "false";
        select.required = false;
        select.classList.add("select-enhanced-source");

        const contenedor = document.createElement("div");
        contenedor.className = "searchable-select";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "searchable-select__input";
        input.autocomplete = "off";
        input.setAttribute("role", "combobox");
        input.setAttribute("aria-expanded", "false");
        input.required = originalRequired;

        const lista = document.createElement("div");
        lista.className = "searchable-select__list";
        lista.setAttribute("role", "listbox");

        contenedor.appendChild(input);
        contenedor.appendChild(lista);
        select.insertAdjacentElement("afterend", contenedor);

        instances.set(select, { contenedor, input, lista });
        refrescarPlaceholder(select, input);
        renderizarOpciones(select, contenedor, "");

        input.addEventListener("focus", () => {
            cerrarTodos(contenedor);
            contenedor.classList.add("is-open");
            input.setAttribute("aria-expanded", "true");
            input.select();
            renderizarOpciones(select, contenedor, "");
        });

        input.addEventListener("input", () => {
            contenedor.classList.add("is-open");
            input.setCustomValidity("");
            renderizarOpciones(select, contenedor, input.value);
        });

        input.addEventListener("keydown", (event) => {
            const opciones = Array.from(lista.querySelectorAll(".searchable-select__option:not(:disabled)"));
            const actual = document.activeElement;

            if (event.key === "Escape") {
                contenedor.classList.remove("is-open");
                input.blur();
            }

            if (event.key === "ArrowDown") {
                event.preventDefault();
                contenedor.classList.add("is-open");
                (opciones[0] || input).focus();
            }

            if (event.key === "Enter" && actual === input && opciones.length === 1) {
                event.preventDefault();
                opciones[0].click();
            }
        });

        lista.addEventListener("keydown", (event) => {
            const opciones = Array.from(lista.querySelectorAll(".searchable-select__option:not(:disabled)"));
            const index = opciones.indexOf(document.activeElement);

            if (event.key === "ArrowDown") {
                event.preventDefault();
                (opciones[index + 1] || opciones[0] || input).focus();
            }

            if (event.key === "ArrowUp") {
                event.preventDefault();
                (opciones[index - 1] || input).focus();
            }

            if (event.key === "Escape") {
                contenedor.classList.remove("is-open");
                input.focus();
            }
        });

        select.addEventListener("change", () => {
            refrescarPlaceholder(select, input);
            renderizarOpciones(select, contenedor, input.value);
        });
    }

    function refrescarSelectsBuscables() {
        document.querySelectorAll("select").forEach((select) => {
            crearSelectBuscable(select);
            const estado = instances.get(select);
            if (!estado) return;
            refrescarPlaceholder(select, estado.input);
            renderizarOpciones(select, estado.contenedor, estado.input.value);
        });
    }

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".searchable-select")) {
            cerrarTodos(null);
        }
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (!form || !form.querySelectorAll) return;

        const selects = form.querySelectorAll("select.select-enhanced-source[data-original-required='true']");
        for (const select of selects) {
            const estado = instances.get(select);
            if (!estado || select.value) continue;
            estado.input.setCustomValidity("Selecciona una opcion");
            estado.input.reportValidity();
            event.preventDefault();
            return;
        }
    }, true);

    document.addEventListener("DOMContentLoaded", refrescarSelectsBuscables);
    window.refrescarSelectsBuscables = refrescarSelectsBuscables;
})();
