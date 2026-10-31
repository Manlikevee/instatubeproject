import logging
import os
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .youtube_service import YouTubeSetupError, YouTubeUploadError, oauth_flow, upload_to_youtube

logger = logging.getLogger(__name__)


def _safe_return_path(request, value):
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return "/"


def _redirect_uri(request):
    return os.getenv("YOUTUBE_REDIRECT_URI", "").strip() or request.build_absolute_uri(reverse("youtube_callback"))


def _fetch_oauth_token(flow, request, redirect_uri):
    """Allow OAuthlib's HTTP exception only for the app's local debug callback."""
    callback_url = request.build_absolute_uri()
    callback_parts = urlparse(callback_url)
    configured_parts = urlparse(redirect_uri)
    loopback_hosts = {"localhost", "127.0.0.1", "::1", "[::1]"}
    local_http = (
        settings.DEBUG
        and callback_parts.scheme == configured_parts.scheme == "http"
        and callback_parts.hostname in loopback_hosts
        and configured_parts.hostname in loopback_hosts
    )
    prior_value = os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
    try:
        if local_http:
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        flow.fetch_token(authorization_response=callback_url)
    finally:
        os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
        if prior_value is not None:
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = prior_value


@require_GET
def youtube_connect(request):
    return_to = _safe_return_path(request, request.GET.get("next", "/"))
    redirect_uri = _redirect_uri(request)
    try:
        flow = oauth_flow(redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent",
        )
        request.session["youtube_oauth_state"] = state
        # google-auth-oauthlib enables PKCE by default; preserve its verifier
        # across the round trip so the authorization-code exchange can succeed.
        request.session["youtube_oauth_code_verifier"] = flow.code_verifier
        request.session["youtube_return_to"] = return_to
        return redirect(auth_url)
    except YouTubeSetupError as exc:
        return render(request, "video_viewer/youtube_result.html", {"error": str(exc), "return_to": return_to})


@require_GET
def youtube_callback(request):
    return_to = _safe_return_path(request, request.session.pop("youtube_return_to", "/"))
    state = request.session.pop("youtube_oauth_state", None)
    code_verifier = request.session.pop("youtube_oauth_code_verifier", None)
    if request.GET.get("error"):
        request.session["youtube_flash"] = "YouTube authorization was cancelled."
        return redirect(return_to)
    try:
        if not state or request.GET.get("state") != state:
            raise YouTubeSetupError("YouTube authorization state did not match. Start Connect YouTube again in the same browser.")
        if not code_verifier:
            raise YouTubeSetupError("The OAuth session expired before completing. Start Connect YouTube again in the same browser.")
        redirect_uri = _redirect_uri(request)
        flow = oauth_flow(redirect_uri, state=state, code_verifier=code_verifier)
        _fetch_oauth_token(flow, request, redirect_uri)
        request.session["youtube_credentials"] = flow.credentials.to_json()
        request.session["youtube_flash"] = "YouTube channel connected. Review the rights and visibility, then click Publish to YouTube on the video you want to upload."
    except Exception as exc:
        logger.exception("YouTube OAuth callback failed")
        request.session["youtube_flash"] = str(exc) if isinstance(exc, YouTubeSetupError) else f"YouTube OAuth failed ({type(exc).__name__}): {str(exc)[:220]}"
    return redirect(return_to)


@require_POST
def youtube_disconnect(request):
    request.session.pop("youtube_credentials", None)
    request.session["youtube_flash"] = "YouTube channel disconnected from this browser session."
    return redirect(_safe_return_path(request, request.POST.get("return_to", "/")))


@require_POST
def youtube_publish(request):
    return_to = _safe_return_path(request, request.POST.get("return_to", "/"))
    if request.POST.get("rights_confirmed") != "on":
        return render(request, "video_viewer/youtube_result.html", {
            "error": "Confirm that you own or are authorized to publish this video before uploading.",
            "return_to": return_to,
        })
    try:
        video_id = upload_to_youtube(
            request.session,
            request.POST.get("video_url", ""),
            request.POST.get("title", ""),
            request.POST.get("description", ""),
            request.POST.get("privacy_status", "public"),
        )
        return render(request, "video_viewer/youtube_result.html", {
            "video_id": video_id, "return_to": return_to,
        })
    except (YouTubeSetupError, YouTubeUploadError) as exc:
        return render(request, "video_viewer/youtube_result.html", {"error": str(exc), "return_to": return_to})
    except Exception:
        logger.exception("Unexpected YouTube upload error")
        return render(request, "video_viewer/youtube_result.html", {
            "error": "The upload failed unexpectedly. Check the server log and try again.",
            "return_to": return_to,
        })
