"""Traducciones al español de los tipos de queja más frecuentes (el dataset los publica en inglés)."""

from __future__ import annotations

TIPOS_QUEJA = {
    "Illegal Parking": "Estacionamiento ilegal",
    "Noise - Residential": "Ruido residencial",
    "HEAT/HOT WATER": "Calefacción / agua caliente",
    "Blocked Driveway": "Entrada de garaje bloqueada",
    "Noise - Street/Sidewalk": "Ruido en calle / acera",
    "UNSANITARY CONDITION": "Condición insalubre (vivienda)",
    "Street Condition": "Estado de la calzada",
    "PLUMBING": "Plomería (vivienda)",
    "Water System": "Sistema de agua",
    "Abandoned Vehicle": "Vehículo abandonado",
    "Dirty Condition": "Suciedad en vía pública",
    "PAINT/PLASTER": "Pintura / yeso (vivienda)",
    "Noise - Commercial": "Ruido comercial",
    "Noise": "Ruido (DEP: obras, equipos)",
    "Traffic Signal Condition": "Semáforo dañado",
    "DOOR/WINDOW": "Puerta / ventana (vivienda)",
    "Encampment": "Campamento en vía pública",
    "Noise - Vehicle": "Ruido de vehículo",
    "WATER LEAK": "Fuga de agua (vivienda)",
    "Derelict Vehicles": "Vehículo deteriorado",
    "Missed Collection": "Recolección no realizada",
    "Illegal Dumping": "Vertido ilegal de basura",
    "GENERAL": "General (vivienda)",
    "General Construction/Plumbing": "Construcción / plomería (DOB)",
    "Damaged Tree": "Árbol dañado",
    "Snow or Ice": "Nieve o hielo",
    "Street Light Condition": "Alumbrado público",
    "ELECTRIC": "Electricidad (vivienda)",
    "Homeless Person Assistance": "Asistencia a persona sin hogar",
    "Rodent": "Roedores",
    "Sidewalk Condition": "Estado de la acera",
    "Non-Emergency Police Matter": "Asunto policial no urgente",
    "Graffiti": "Grafiti",
    "Sewer": "Alcantarillado",
    "Consumer Complaint": "Queja de consumidor",
    "Taxi Complaint": "Queja de taxi",
    "Building/Use": "Uso de edificio (DOB)",
    "Lead": "Plomo (pintura)",
    "Indoor Air Quality": "Calidad del aire interior",
    "Elevator": "Ascensor",
    "Animal-Abuse": "Maltrato animal",
    "Vendor Enforcement": "Venta ambulante",
    "Overgrown Tree/Branches": "Ramas / árbol crecido",
    "New Tree Request": "Solicitud de árbol nuevo",
    "Obstruction": "Obstrucción de la vía",
    "Litter Basket Request": "Solicitud de papelera",
    "APPLIANCE": "Electrodomésticos (vivienda)",
    "FLOORING/STAIRS": "Pisos / escaleras (vivienda)",
    "SAFETY": "Seguridad (vivienda)",
    "Smoking or Vaping": "Fumar o vapear",
    "Root/Sewer/Sidewalk Condition": "Raíces / acera (árboles)",
    "Drug Activity": "Actividad de drogas",
}

BOROUGHS_ES = {
    "BRONX": "Bronx",
    "BROOKLYN": "Brooklyn",
    "MANHATTAN": "Manhattan",
    "QUEENS": "Queens",
    "STATEN ISLAND": "Staten Island",
    "SIN DATO": "Sin dato",
}


def tipo_es(tipo: str) -> str:
    """Nombre en español (o el original si no está en el diccionario)."""
    return TIPOS_QUEJA.get(tipo, tipo)
