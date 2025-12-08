"""
Celery task-ovi za generisanje QR kodova.
"""
import os
import hashlib
import requests
from onetouch import celery, logger


@celery.task(bind=True, max_retries=3, name='onetouch.tasks.generate_qr_code')
def generate_qr_code_async(self, qr_data, student_id, project_folder, user_id):
    """
    Asinhrono generiše QR kod sa caching-om.

    Args:
        self: Task instanca
        qr_data: Dict sa podacima za QR kod (NBS format)
        student_id: ID učenika
        project_folder: Putanja do projekta
        user_id: ID korisnika

    Returns:
        str: Putanja do QR kod slike, ili None ako ne uspe
    """
    try:
        # Generiši cache key na osnovu qr_data
        cache_key_str = str(sorted(qr_data.items()))
        cache_key = hashlib.md5(cache_key_str.encode()).hexdigest()

        # Cache folder
        cache_dir = os.path.join(project_folder, 'static', 'qr_cache')
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        cache_file = os.path.join(cache_dir, f'{cache_key}.png')

        # Proveri cache
        if os.path.exists(cache_file):
            logger.info(f'[QR Task {self.request.id}] Cache hit: {cache_key}')
            return cache_file

        # Generiši novi QR kod
        logger.info(f'[QR Task {self.request.id}] Generating new QR code for student {student_id}')

        response = requests.post(
            'https://nbs.rs/QRcode/api/qr/v1/gen/250',
            json=qr_data,
            timeout=10  # 10 sekundi timeout
        )

        if response.status_code == 200:
            # Sačuvaj u cache
            with open(cache_file, 'wb') as f:
                f.write(response.content)

            logger.info(f'[QR Task {self.request.id}] QR code generated: {cache_key}')
            return cache_file
        else:
            logger.error(f'[QR Task {self.request.id}] NBS API returned {response.status_code}')
            return None

    except requests.Timeout:
        logger.error(f'[QR Task {self.request.id}] NBS API timeout')
        # Retry
        raise self.retry(countdown=30)
    except Exception as e:
        logger.error(f'[QR Task {self.request.id}] Error generating QR code: {str(e)}')
        # Retry
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30)
        return None
