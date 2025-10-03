import Stripe from 'stripe';
import { v4 as uuidv4 } from 'uuid';
import { DATABASE_URL } from '../config.js'; // Variables de Render
import { sendEmail } from '../utils/emailService.js';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

// Crear sesión de pago para profesionales de salud ($120 a $180)
export const createProfessionalPayment = async (req, res) => {
    try {
        const { amount, email, name } = req.body;

        if (!amount || !email || !name) {
            return res.status(400).json({ message: 'Faltan datos obligatorios' });
        }

        if (amount < 120 || amount > 180) {
            return res.status(400).json({ message: 'Monto fuera del rango permitido para profesionales' });
        }

        const paymentIntent = await stripe.paymentIntents.create({
            amount: amount * 100,
            currency: 'usd',
            receipt_email: email,
            metadata: { name, type: 'professional' }
        });

        // Guardar en base de datos real usando DATABASE_URL
        const professionalRecord = {
            id: uuidv4(),
            name,
            email,
            amount,
            paymentIntentId: paymentIntent.id,
            status: 'pending',
            createdAt: new Date()
        };
        // Inserta professionalRecord en tu DB real

        // Enviar correo de confirmación
        await sendEmail({
            to: email,
            subject: 'Confirmación de pago profesional',
            text: `Hola ${name}, tu pago de $${amount} ha sido iniciado. ID: ${paymentIntent.id}`
        });

        res.json({
            clientSecret: paymentIntent.client_secret,
            message: 'Pago profesional iniciado correctamente'
        });
    } catch (error) {
        console.error('Error en createProfessionalPayment:', error);
        res.status(500).json({ message: 'Error al procesar el pago profesional' });
    }
};

// Confirmar pago webhook (opcional)
export const confirmProfessionalPayment = async (paymentIntentId) => {
    try {
        // Actualizar estado en DB a 'completed' usando paymentIntentId
        // Ejemplo: UPDATE professionals SET status='completed' WHERE paymentIntentId=...
    } catch (error) {
        console.error('Error al confirmar pago profesional:', error);
    }
};
