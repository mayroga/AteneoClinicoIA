import Stripe from 'stripe';
import { v4 as uuidv4 } from 'uuid';
import { DATABASE_URL } from '../config.js'; // Asumiendo que tienes un config que obtiene variables de Render
import { sendEmail } from '../utils/emailService.js'; // Función para enviar correos

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

// Crear sesión de pago para voluntarios ($40 a $50)
export const createVolunteerPayment = async (req, res) => {
    try {
        const { amount, email, name } = req.body;

        if (!amount || !email || !name) {
            return res.status(400).json({ message: 'Faltan datos obligatorios' });
        }

        const paymentIntent = await stripe.paymentIntents.create({
            amount: amount * 100, // Stripe maneja centavos
            currency: 'usd',
            receipt_email: email,
            metadata: { name, type: 'volunteer' }
        });

        // Guardar en base de datos (simulación real, adaptarlo a tu DB)
        const volunteerRecord = {
            id: uuidv4(),
            name,
            email,
            amount,
            paymentIntentId: paymentIntent.id,
            status: 'pending',
            createdAt: new Date()
        };
        // Aquí insertas volunteerRecord en tu DB real usando DATABASE_URL

        // Enviar correo de confirmación
        await sendEmail({
            to: email,
            subject: 'Confirmación de pago voluntario',
            text: `Hola ${name}, tu pago de $${amount} ha sido iniciado. ID: ${paymentIntent.id}`
        });

        res.json({
            clientSecret: paymentIntent.client_secret,
            message: 'Pago iniciado correctamente'
        });
    } catch (error) {
        console.error('Error en createVolunteerPayment:', error);
        res.status(500).json({ message: 'Error al procesar el pago voluntario' });
    }
};

// Confirmar pago webhook (opcional si quieres manejar desde Stripe)
export const confirmVolunteerPayment = async (paymentIntentId) => {
    try {
        // Actualizar estado en DB a 'completed' usando paymentIntentId
        // Ejemplo: UPDATE volunteers SET status='completed' WHERE paymentIntentId=...
    } catch (error) {
        console.error('Error al confirmar pago voluntario:', error);
    }
};
