import cv2

import matplotlib.pyplot as plt
from tqdm import tqdm
import csv

class Analyser:
    def __init__(self):
        pass

    def compute_chemotaxis(self, video_path):
        #self.logger.log("Computing chemotaxis")
        print(f"Computing chemotaxis for {video_path}")
        # self.logger.log("Starting compression of %s" % folder_name)

        # Call the load_video function
        cap, width, height = self.load_video(video_path)

        # Read the first frame
        ret, first_frame = cap.read()
        first_frame = self.get_specific_frame(video_path, 3)

        if not ret:
            print("Error: Could not read the first frame.")
            return

        # Detect edges in the first frame
        # edges = detect_petri_edges(first_frame)

        # Detect circles
        # detected_circles = detect_circles(edges)

        # Save the first frame with detected circles
        # draw_circles(first_frame, detected_circles)

        # get middle of the image width
        middle = int(width / 2)

        # Remove background
        positions = self.locate_worms(video_path)

        # Compute chemotaxis index
        chemotaxis_index_by_frame = self.compute_chemotaxis_index(positions, middle)

        # Save centers of mass to CSV file
        # save_centers_to_csv(positions, 'centers.csv')

        # Save chemotaxis indices to CSV file
        self.save_chemotaxis_indices_to_csv(chemotaxis_index_by_frame, 'chemotaxis_indices.csv')

        # Plot chemotaxis index
        self.plot_chemotaxis_index(chemotaxis_index_by_frame)

        # Release the video capture object when done
        cap.release()

    def get_specific_frame(self, video_path, frame_number):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return None  # Return None to indicate an error

        # Set the position to the desired frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number - 1)  # Adjust for 0-based indexing

        # Read the specific frame
        ret, frame = cap.read()

        # Check if the frame was successfully read
        if not ret:
            print(f"Error: Could not read frame {frame_number}.")
            return None  # Return None to indicate an error

        # Release the video capture object when done (do not close OpenCV windows here)
        cap.release()

        # Return the frame
        return frame

    def load_video(self, video_path):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return None

        # Get the video's frames per second (fps) and frame dimensions
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"Video loaded successfully. FPS: {fps}, Resolution: {width}x{height}")

        return cap, width, height

    def detect_petri_edges(self, frame):
        # Convert the frame to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply GaussianBlur to reduce noise and help edge detection
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)

        # Apply binary thresholding
        _, binary_frame = cv2.threshold(blurred, 50, 255, cv2.THRESH_BINARY)

        # Use Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)

        # cv2.imshow("Binary Frame", binary_frame)

        return edges, binary_frame

    def detect_circles(self, binary_frame, max_distance_from_center=200):
        # Hough Circle Transform parameters
        dp = 1  # Inverse ratio of the accumulator resolution to the image resolution
        min_dist = 500  # Minimum distance between the centers of detected circles
        param1 = 50  # Upper threshold for the internal Canny edge detector
        param2 = 10  # Threshold for center detection
        min_radius = 900  # Minimum radius to be detected
        max_radius = 1500  # Maximum radius to be detected

        # cv2.imshow("Binary Frame", binary_frame)
        # cv2.waitKey(0)

        # Apply Hough Circle Transform
        circles = cv2.HoughCircles(binary_frame, cv2.HOUGH_GRADIENT, dp=dp, minDist=min_dist,
                                   param1=param1, param2=param2, minRadius=min_radius, maxRadius=max_radius)

        if circles is not None:
            # Extract the first detected circle
            circle = circles[0, 0]

            # Reduce the radius by a specific value (adjust as needed)
            circle[2] -= 210

            # Return center and radius
            center = (int(circle[0]), int(circle[1]))
            radius = int(circle[2])

            return center, radius

        return None

    def draw_circles(self, frame, circle_info):
        # not used
        print("draw_circles")
        if circle_info is not None:
            # Convert circle coordinates to integers
            circle_center, circle_radius = circle_info
            circle_center = tuple(map(int, circle_center))
            circle_radius = int(circle_radius)

            # Draw the circle on the frame
            cv2.circle(frame, circle_center, circle_radius, (0, 255, 0), 2)

            # Resize the frame to 50% of its original size
            resized_frame = cv2.resize(frame, (int(frame.shape[1] * 0.5), int(frame.shape[0] * 0.5)))

            # Display the annotated and resized frame
            # cv2.imshow("Annotated and Resized Frame", resized_frame)

            # Wait for a key event and then close the display window
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        else:
            print("No circle detected.")

    def locate_worms(self, video_path, detected_circles=None, min_element_area_threshold=30, stop_at_frame=50):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return

        # Create a background subtractor
        bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16.0, detectShadows=False)

        # Dictionary to store the centers of mass for each frame
        all_centers_by_frame = {}

        # Initialize progress bar
        progress_bar = tqdm(total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), desc="Removing Background")

        frame_index = 0  # Index to keep track of the frame number

        # # Check if circles are detected
        # if detected_circles is not None:
        #     # Convert circle coordinates to integers
        #     circle_center, circle_radius = detected_circles
        #     circle_center = tuple(map(int, circle_center))
        #     circle_radius = int(circle_radius)
        #
        # else:
        #     print("No circle detected.")
        #     return

        while True:
            # Read a frame from the video
            ret, frame = cap.read()

            if not ret:
                print("End of video stream.")
                break

            # Apply background subtraction
            fg_mask = bg_subtractor.apply(frame)

            # Set the transparency of the foreground mask
            alpha = 0.5

            # # Create a mask for the detected circle
            # circle_mask = np.zeros_like(fg_mask)
            # cv2.circle(circle_mask, circle_center, circle_radius, (255, 255, 255), thickness=cv2.FILLED)
            #
            # # Apply the mask to the foreground mask
            # fg_mask = cv2.bitwise_and(fg_mask, circle_mask)

            # Remove small elements in the mask based on area threshold
            _, fg_mask_thresh = cv2.threshold(fg_mask, 128, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(fg_mask_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # List to store centers of mass for the current frame
            centers_of_mass = []

            for contour in contours:
                if cv2.contourArea(contour) >= min_element_area_threshold:
                    # Calculate the center of mass
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        center_of_mass = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        centers_of_mass.append(center_of_mass)

            # Store centers of mass for the current frame in the dictionary
            all_centers_by_frame[frame_index] = centers_of_mass

            # Increment frame index
            frame_index += 1

            # # Convert the foreground mask to a 3-channel image
            # fg_mask_color = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)
            #
            # # Display the foreground mask in red
            # fg_mask_color[np.where((fg_mask_color == [255, 255, 255]).all(axis=2))] = [0, 0, 255]
            #
            # # Draw a '+' at each center of mass
            # for center_of_mass in centers_of_mass:
            #     cv2.drawMarker(frame, center_of_mass, (0, 255, 0), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2)
            #
            # # Blend the original frame and the foreground mask
            # result = cv2.addWeighted(frame, 1 - alpha, fg_mask_color, alpha, 0)
            #
            # # Resize the result frame by 0.5
            # result_resized = cv2.resize(result, (int(result.shape[1] * 0.80), int(result.shape[0] * 0.80)))
            #
            # # Display the blended and resized result
            # cv2.imshow("Blended and Resized Result", result_resized)
            #
            # # Press 'q' to exit the loop and close the windows
            # if cv2.waitKey(30) & 0xFF == ord('q') or frame_index == stop_at_frame:
            #     break

            # Update progress bar
            progress_bar.update(1)

        # Release the video capture object when done
        cap.release()
        cv2.destroyAllWindows()

        return all_centers_by_frame

    def compute_chemotaxis_index(self, all_centers_by_frame, middle):
        # Dictionary to store chemotaxis index for each frame
        chemotaxis_index_by_frame = {}

        # if detected_circles is not None:
        #     # Convert circle coordinates to integers
        #     circle_center, circle_radius = detected_circles
        #     circle_center = tuple(map(int, circle_center))
        #     circle_radius = int(circle_radius)
        #
        # else:
        #     print("No circle detected.")
        #     return chemotaxis_index_by_frame

        # Iterate over frames
        for frame_index, centers_of_mass in all_centers_by_frame.items():
            print(f"Frame {frame_index}: {len(centers_of_mass)} points detected.")

            # Define the left and right boundaries of the circle
            # left_boundary = circle_center[0] - circle_radius
            # right_boundary = circle_center[0] + circle_radius

            # Count points on the left and right sides of the circle
            # left_points = sum(1 for center in centers_of_mass if left_boundary <= center[0] < circle_center[0])
            # right_points = sum(1 for center in centers_of_mass if circle_center[0] < center[0] <= right_boundary)

            left_points = sum(1 for center in centers_of_mass if center[0] < middle)
            right_points = sum(1 for center in centers_of_mass if center[0] > middle)

            # Compute chemotaxis index
            total_points = len(centers_of_mass)
            chemotaxis_index = left_points / total_points if total_points > 0 else 0.0

            print(
                f"Frame {frame_index}: {left_points} points on the left, {right_points} points on the right, chemotaxis index = {chemotaxis_index}")

            # Store chemotaxis index for the current frame
            chemotaxis_index_by_frame[frame_index] = chemotaxis_index

        return chemotaxis_index_by_frame

    def save_centers_to_csv(self, centers_list, csv_filename):
        """
        Save the list of center of mass to a CSV file.

        Parameters:
        - centers_list: List of center of mass, where each element is a tuple (x, y).
        - csv_filename: Name of the CSV file to save.

        Example:
        save_centers_to_csv([(1, 2), (3, 4), (5, 6)], 'centers.csv')
        """
        with open(csv_filename, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['Frame', 'X', 'Y'])  # Writing header

            for frame, centers in enumerate(centers_list, start=1):
                for center in centers:
                    csv_writer.writerow([frame, center[0], center[1]])

    def save_chemotaxis_indices_to_csv(self, chemotaxis_indices, csv_filename):
        """
        Save the chemotaxis indices to a CSV file.

        Parameters:
        - chemotaxis_indices: List of chemotaxis indices for each frame.
        - csv_filename: Name of the CSV file to save.

        Example:
        save_chemotaxis_indices_to_csv([0.1, 0.2, 0.3], 'chemotaxis_indices.csv')
        """
        with open(csv_filename, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['Frame', 'Chemotaxis Index'])  # Writing header

            for frame, chemotaxis_index in enumerate(chemotaxis_indices, start=1):
                csv_writer.writerow([frame, chemotaxis_index])

    def plot_chemotaxis_index(self, chemotaxis_index_by_frame, frame_rate=2, output_prefix="chemotaxis_plot", font_size=14):
        # Calculate time in minutes for each frame
        time_in_minutes = [frame_index * frame_rate / 60 for frame_index in sorted(chemotaxis_index_by_frame.keys())]

        # Extract chemotaxis index values
        chemotaxis_values = [chemotaxis_index_by_frame[frame_index] for frame_index in
                             sorted(chemotaxis_index_by_frame.keys())]

        # Plot chemotaxis index with respect to time
        plt.figure(figsize=(10, 6))
        plt.plot(time_in_minutes, chemotaxis_values, marker='o', linestyle='-', color='b')
        plt.title('Chemotaxis Index Over Time', fontsize=font_size)
        plt.xlabel('Time (minutes)', fontsize=font_size)
        plt.ylabel('Chemotaxis Index', fontsize=font_size)
        plt.xticks(fontsize=font_size)
        plt.yticks(fontsize=font_size)

        # Save the plot as PDF and PNG
        pdf_filename = f"{output_prefix}.pdf"
        png_filename = f"{output_prefix}.png"

        plt.savefig(pdf_filename, format='pdf')
        plt.savefig(png_filename, format='png')