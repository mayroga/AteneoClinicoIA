// JS básico para validaciones o interacciones
document.addEventListener("DOMContentLoaded", function() {
    console.log("Ateneo Clínico IA: Scripts cargados.");

    // Ejemplo: alerta al enviar formulario
    const forms = document.querySelectorAll("form");
    forms.forEach(form => {
        form.addEventListener("submit", function() {
            console.log("Formulario enviado");
        });
    });
});
