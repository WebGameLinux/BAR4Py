import cv2
import numpy as np
from shortfuncs import *
from marker import Marker

# MarkerDetector

class MarkerDetector:
    '''
    MarkerDetector Class, 2016/12/9 Edit

    Inputs:
    markerDetector is MarkerDetector object
    dictionary is Dictionary object
    cameraParameters is CameraParameters object

    For examples:
    >>> from bar4py.markerdetect import MarkerDetector
    >>> detector = MarkerDetector()
    >>> detector = MarkerDetector(markerDetector=detector)
    >>> detector = MarkerDetector(dictionary=dictionary)
    >>> detector = MarkerDetector(cameraParameters=cameraParameters)
    >>> detector = MarkerDetector(dictionary=dictionary, cameraParameters=cameraParameters)
    '''
    def __init__(self, markerDetector=None, dictionary=None, cameraParameters=None):
        # Default parameters
        self.dictionary = None
        self.cameraParameters = None

        # If input MakerDetector object
        if markerDetector is not None:
            self.dictionary = markerDetector.dictionary
            self.cameraParameters = markerDetector.cameraParameters

        # Dictionary object
        if dictionary is not None:
            if dictionary.isPooled():
                self.dictionary = dictionary
            else:
                raise TypeError('Please input pooled dictionary')

        # CameraParameters object
        if cameraParameters is not None:
            if cameraParameters.camera_matrix is not None:
                self.cameraParameters = cameraParameters
            else:
                raise TypeError('Please set cameraParameters.camera_matrix')


    def isProbableMarker(self, approx_curve, limit=32):
        '''
        If probable to return True, else return False
        '''
        if approx_curve.shape != (4,1,2): return False
        if (min(np.sum((approx_curve[0] - approx_curve[2])**2),
                np.sum((approx_curve[1] - approx_curve[3])**2))
            >= limit**2): return True

    def localRect(self, corners):
        x0, y0 = corners[:,1].min(), corners[:,0].min()
        x1, y1 = corners[:,1].max(), corners[:,0].max()
        return np.array([x0, y0, x1, y1], dtype='uint32').reshape(2,2)

    def localFrame(self, rect, frame):
        return frame[rect[0,0]:rect[1,0], rect[0,1]:rect[1,1]]

    def localCorners(self, rect, corners):
        local_corners = np.zeros((4,2), dtype=corners.dtype)
        local_corners[:,0] = corners[:,0] - rect[0,1]
        local_corners[:,1] = corners[:,1] - rect[0,0]
        return local_corners

    def recognize(self, points, frame, dictionary=None, limit=0.8, side_length=42, batch_size=3):
        '''
        Inputs:
        points is marker.points param
        frame is image frame
        dictionary is Dictionary object
        ...

        Outputs:
        marker_id, rotations

        >>> marker_i, rotations = detector.recognize(points, frame, dictionary=dictionary)
        '''
        dictionary = dictionary or self.dictionary
        if dictionary is None: raise TypeError('recognize nead dictionary')

        # To Gray
        gray = frame
        if len(gray.shape) == 3: gray = bgr2gray(frame)

        # Convert the points, gray to local_points, local_gray
        rect = self.localRect(points)
        gray = self.localFrame(rect, gray)
        points = self.localCorners(rect, points)

        # Define src_points and dst_points, src: 0,1,2,3 -> dst: 1,0,3,2
        points_src = np.float32(points)
        points_dst = np.float32([[0,side_length],[0,0], 
                                 [side_length,0],[side_length,side_length]])
    

        # Calc transform matrix and perspective dst map
        M = cv2.getPerspectiveTransform(points_src, points_dst)
        dst = cv2.warpPerspective(gray, M, (side_length, side_length))

        # Begin recognize
        _, dst = cv2.threshold(dst, dst.mean(), 1, cv2.THRESH_OTSU)
        # Probables
        probables = []
        for marker_id, hash_map in dictionary.getDict():
            deviation = rotations = 0
            for i in range(4):
                now_deviation = np.sum((dst == hash_map).astype(int)) / (side_length**2)
                if now_deviation > deviation: deviation, rotations = now_deviation, i
                hash_map = np.rot90(hash_map)
            if deviation > limit:
                probables.append((deviation, marker_id, rotations))
                if len(probables) > batch_size: break
        # Best of marker_id and rotations
        if len(probables) > 0:
            return max(probables, key=lambda item:item[0])[1:]

    def detect(self, frame, epsilon_rate=0.01):
        '''
        Inputs:
        frame is image frame

        Outputs:
        markers is Marker object list

        >>> markers = detector.detect(frame)
        '''
        # Output marker list
        markers = []

        # To Gray
        gray = frame
        if len(gray.shape) == 3: gray = bgr2gray(frame)

        # Thresh
        ret, thresh = cv2.threshold(gray, gray.mean(), 255,
                                    cv2.THRESH_BINARY)
        if not ret: return False

        # Find contours
        _, contours, _ = cv2.findContours(thresh, cv2.RETR_LIST,
                                          cv2.CHAIN_APPROX_NONE)

        # Probable Marker
        _markers = []
        for cnt in contours:
            epsilon = epsilon_rate * cv2.arcLength(cnt,True)
            approx_curve = cv2.approxPolyDP(cnt,epsilon,True)
            if self.isProbableMarker(approx_curve):
                points = approx_curve.reshape(4,2)
                _markers.append(Marker(points=points))

        # Matched Marker
        if self.dictionary is not None:
            for marker in _markers:
                rst = self.recognize(marker.points, gray)
                if rst:
                    marker.marker_id, marker.rotations = rst
                    marker.calculateCorners(gray)
                    markers.append(marker)
        else:
            markers = _markers

        # Calculate Extrinsics
        if self.cameraParameters is not None:
            for marker in markers:
                marker.calculateExtrinsics(self.cameraParameters)

        return markers
