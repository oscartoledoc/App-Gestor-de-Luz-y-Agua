# ⚡💧 Gestor de Consumos (Utilities Manager)

<div align="center">
  <img src="https://i.imgur.com/ApFJxSE.png" alt="Logo Gestor de Consumos" width="150">
  <br>
  <br>
  
  ![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
  ![Flask](https://img.shields.io/badge/Flask-2.0%2B-black?style=for-the-badge&logo=flask)
  ![Firebase](https://img.shields.io/badge/Firebase-Firestore-orange?style=for-the-badge&logo=firebase)
  ![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.0-38B2AC?style=for-the-badge&logo=tailwind-css)
</div>

## 📖 Descripción

**Gestor de Consumos** es una aplicación web diseñada para administrar, calcular y prorratear los gastos de servicios básicos (Luz y Agua) en un entorno multifamiliar. 

El sistema resuelve la problemática de compartir un único medidor entre varias familias, permitiendo registrar lecturas individuales, calcular el consumo exacto y distribuir los costos fijos del recibo de manera proporcional según reglas de negocio personalizadas.

## 🚀 Características Principales

* **Gestión de Lecturas:** Registro histórico de lecturas de medidores con detección automática de la "lectura anterior" basada en fechas.
* **Cálculo Automático:** Determina el consumo (Lectura Actual - Anterior) y calcula el costo base según tarifas configurables.
* **Lógica de Prorrateo Avanzada:** Distribución inteligente de costos fijos (Cargo fijo, Alumbrado, Alcantarillado) entre inquilinos:
    * *Familia 1:* Asume el 13% de los costos fijos.
    * *Otras Familias:* Asumen el 43.5% respectivamente.
* **Cálculo de Impuestos:** Aplicación automática del IGV (18%) sobre la base imponible total (Consumo + Extras).
* **Panel de Configuración:** Interfaz para actualizar nombres de familias, precios por kWh/m³ y porcentajes de impuestos sin tocar el código.
* **Filtrado Dinámico:** Visualización de historiales filtrados por Familia o Tipo de Servicio en tiempo real.
* **Interfaz Moderna:** Diseño limpio y responsivo utilizando Tailwind CSS.

## 🛠️ Estructura del Proyecto (MVC)

El proyecto sigue una arquitectura modular para facilitar la escalabilidad y el mantenimiento:

```text
/
├── api/
│   └── index.py          # Punto de entrada (Entry Point)
├── app/
│   ├── __init__.py       # Inicialización de Flask y Firebase
│   ├── config.py         # Variables de configuración y constantes
│   ├── routes.py         # Controladores y definición de rutas
│   ├── services.py       # Capa de acceso a datos (Firestore)
│   ├── utils.py          # Lógica matemática y helpers
│   └── templates/        # Vistas (HTML + Jinja2 + Tailwind)
├── requirements.txt      # Dependencias del proyecto
└── vercel.json           # Configuración de despliegue
